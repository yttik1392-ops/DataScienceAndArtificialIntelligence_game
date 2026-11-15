"""졸업할 수 있을까? — 4학년 × 2학기 대학 생활 서바이벌

실행: python main.py  (pygame-ce 필요: pip install pygame-ce)
조작: 과제·시험·공부·수업은 아래 CLICK 원에서 왼쪽 클릭
      사랑(하트)·동아리(기타)는 방 안의 랜덤 위치에서 3~4초 내 직접 클릭
      시작/학기 결산: 아무 키 또는 마우스 클릭
      졸업 엔딩: 다양한 분기형 엔딩 + 4년 앨범, 스페이스/→/클릭으로 다음 페이지
      R: 게임 오버·졸업 후 처음부터, M: 배경음악 켜기/끄기, ESC: 종료
음악: 이 파일과 같은 폴더에 music.mp3를 놓으면 시작 시 자동 재생.
      학기 결산에서 잠시 멈췄다가 다음 학기에 이어 재생하며 곡이 끝나면 반복.
      음악의 BPM과 관계없이 노트는 매 학기마다 무작위 타이밍으로 등장.
시험: 기본 40초 후 시험 기간 10초 추가. 짧은 암전 후 과제/시험/공부 폭주.
판정: PERFECT/GREAT는 감점 없음, GOOD 3개=MISS 1개, OK 1개=MISS 2/3개.
      PERFECT/GREAT만 콤보 유지. GOOD/OK/MISS/헛클릭 시 콤보 초기화.
      3콤보부터 PERFECT/GREAT 성공마다 체력 +1 (최대 25).
학점: 학업 노트의 GOOD/OK/MISS를 학기당 3회까지 감점 없이 유예한다.
      A+는 전부 PERFECT일 때만, 3회 유예 안이면 A까지 가능하다.
      유예를 넘는 실수와 감점 비율에 따라 B/C/D/F. F 다음 학기는 체력 20 시작.
      사랑/동아리는 시간 제한 내 클릭하면 성공, 놓치면 실패만 기록한다.
      성공률은 연애/인간관계에만 반영하며 체력, 학점, 콤보, 점수와 무관하다.
      사랑·동아리가 나타나면 학업 노트 판정선 도착에 짧은 여유가 생긴다.
      시작 화면의 [평가 기준 보기] 버튼 또는 H키로 규칙 확인 가능.
"""

import asyncio
import math
import random
from pathlib import Path

import pygame

# 44.1kHz stereo / larger buffer for browser audio (less crackling)
pygame.mixer.pre_init(44100, -16, 2, 4096)
pygame.init()

# ========================= 원하는 대로 바꿀 수 있는 설정 =========================
WIDTH, HEIGHT = 1000, 700
SEMESTER_SECONDS = 40                 # 한 학기의 길이
PHASE_MS = SEMESTER_SECONDS * 1000
EXAM_SECONDS = 10                     # 정규 학기 뒤에 이어지는 시험 기간
EXAM_MS = EXAM_SECONDS * 1000
EXAM_ALERT_MS = 1500                 # "시험 기간이다!!!" 화면 표시 시간
COMBO_HEAL_START = 3                 # PERFECT/GREAT 3연속부터 회복
COMBO_HEAL_AMOUNT = 1               # 콤보 3 이상인 PERFECT/GREAT마다 체력 +1
TARGET = (WIDTH // 2, 560)
TARGET_RADIUS = 57
START_HEALTH = 25
MISS_DAMAGE_NORMAL = 3                 # 수업 외 모든 노트 놓침
MISS_DAMAGE_CLASS = MISS_DAMAGE_NORMAL * 2  # 수업 노트 놓침: 체력 2배 감소
WRONG_CLICK_DAMAGE = 3
SEMESTER_RECOVERY = 4                # F가 아니면 학기 사이 방학 회복
F_NEXT_HEALTH = 20                   # 직전 학기 F면 다음 학기는 체력 20으로 시작
# 학기별 학업 노트 GOOD/OK/MISS 합산 3회까지 학점에서만 유예.
# MISS를 유예받더라도 체력 감소/콤보 초기화는 평소와 동일하다.
GRADE_GRACE_MISTAKES = 3
# MISS가 많거나 GOOD/OK가 누적되면 D/F가 되도록 설정 (학업 노트만)
C_PENALTY_RATIO = 0.10               # 환산 감점 10%부터 최소 C
D_PENALTY_RATIO = 0.16               # 환산 감점 16%부터 최소 D
F_PENALTY_RATIO = 0.35               # 환산 감점 35%부터 F
D_MISS_RATIO = 0.08                  # 실제 MISS 8%부터 최소 D
F_MISS_RATIO = 0.25                  # 실제 MISS 25%부터 F
MUSIC_VOLUME = 0.55                    # 0.0 ~ 1.0
# 같은 폴더에 music.ogg 또는 music.mp3를 넣으면 자동으로 음악 재생
MUSIC_CANDIDATES = ("music.ogg", "music.mp3")

# 사랑·동아리는 아래로 날아오는 노트 대신 원룸 안에 잠깐 나타남.
SOCIAL_LIFETIME_RANGE = (3000, 4000)    # 3~4초 내 클릭: 성공, 미클릭: 실패
SOCIAL_CLICK_RADIUS = 43                # 기존 클릭 반경 유지
# 학업과 병행할 수 있게 사회 이벤트 사이에 조금 더 여유를 줌.
SOCIAL_GAPS = {                         # 학년별 등장 간격(ms)
    1: (4200, 5600),
    2: (4000, 5400),
    3: (3850, 5150),
    4: (3600, 4900),
}
# 사랑·동아리가 등장하는 순간, 학업 노트의 도착 시각만 잠시 비움.
# 노트는 미리 날아올 수 있지만 이 시간에는 판정선에 도달하지 않음.
SOCIAL_BREATH_BEFORE_MS = 220
SOCIAL_BREATH_AFTER_MS = 900

# 학업 노트 전용 감점 단위: 3단위 = MISS 1개
# 사랑/동아리는 오직 성공 횟수 / 전체 등장 횟수만 계산한다.
PENALTY_UNITS = {"PERFECT": 0, "GREAT": 0, "GOOD": 1, "OK": 2, "MISS": 3}
# 순서대로 PERFECT, GREAT, GOOD, OK의 최대 타이밍 오차(ms)
# 마지막 OK 허용 구간 안에서만 클릭 성공. 나머지는 MISS/헛클릭.

# 학업 노트 빈도와 비행 속도. 정확한 판정 시간은 그대로 유지해 학점 난도는 보존.
# (기본 노트 간격 ms, 이동 ms, PERFECT/GREAT/GOOD/OK 허용 오차 ms)
DIFFICULTY = {
    # (노트 간격, 비행 시간, PERFECT, GREAT, GOOD, OK), 단위 ms
    # PERFECT와 GOOD/OK의 최대 허용 시간은 이전과 같고 GREAT만 넓혔다.
    1: (1450, 2400, 45, 86, 100, 135),   # GREAT +16ms
    2: (1050, 2000, 40, 75, 90, 120),    # GREAT +15ms
    3: (760, 1650, 35, 66, 80, 105),     # GREAT +14ms
    4: (560, 1350, 30, 58, 70, 90),      # GREAT +13ms
}
# 빠르게 몰려오는 구간은 남겨두되, 판정 불가능한 겹침은 줄임.
MIN_GAP_MS = {1: 480, 2: 390, 3: 310, 4: 250}

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("졸업할 수 있을까? | 대학 생활 서바이벌")
clock = pygame.time.Clock()
RULES_BUTTON = pygame.Rect(365, 478, 270, 54)
RULES_BACK_BUTTON = pygame.Rect(355, 590, 290, 44)

# ========================= 색상과 폰트 =========================
WALL = (245, 239, 230)
FLOOR = (186, 153, 117)
FLOOR_LINE = (160, 130, 95)
BED_FRAME = (120, 86, 62)
BED_BLANKET = (140, 170, 210)
BED_PILLOW = (245, 245, 245)
DESK = (140, 100, 72)
CHAIR = (90, 90, 100)
MONITOR = (40, 40, 50)
SKY = (163, 210, 255)
CLOUD = (245, 245, 245)
RUG = (190, 180, 220)
SKIN = (249, 214, 183)
PANTS = (50, 60, 90)
SHOES = (255, 255, 255)
CRIMSON = (153, 27, 54)
DARK_CRIMSON = (99, 20, 43)
LIGHT_CRIMSON = (184, 58, 83)
TEXT = (54, 43, 50)
WHITE = (255, 255, 255)
MUTED = (121, 109, 116)

# Windows의 '맑은 고딕'. 다른 OS는 나눔스퀘어/기본 폰트로 대체.
# 웹에서는 Windows 글꼴을 사용할 수 없으므로, 게임 폴더의 글꼴을 우선한다.
# Run prepare_font.py ONCE before pygbag; it downloads Korean TTF from official Google Fonts.
# The font itself is not distributed in this source ZIP.
_local_font = Path(__file__).resolve().parent / "korean.ttf"
font_name = (str(_local_font) if _local_font.is_file() else
             pygame.font.match_font("malgungothic") or
             pygame.font.match_font("nanumsquare") or
             pygame.font.match_font("nanumgothic"))
FONT = pygame.font.Font(font_name, 23)
SMALL_FONT = pygame.font.Font(font_name, 18)
TINY_FONT = pygame.font.Font(font_name, 16)
BIG_FONT = pygame.font.Font(font_name, 38)
TITLE_FONT = pygame.font.Font(font_name, 44)
GRADE_FONT = pygame.font.Font(font_name, 72)
# 사용하는 PC에 따라 일부 이모지는 흑백/네모로 표시될 수 있음.
# Browser lacks Segoe UI Emoji: use embedded PNG pictograms instead of system fonts.
ICON_FILENAMES = {
    "📄": "paper.png", "📝": "exam.png", "📚": "books.png",
    "🏫": "school.png", "💗": "heart.png", "🎸": "guitar.png",
}
ICON_CACHE = {}

def get_event_icon(emoji, size=38):
    key = (emoji, size)
    if key not in ICON_CACHE:
        filename = ICON_FILENAMES.get(emoji)
        if not filename:
            return None
        path = Path(__file__).resolve().parent / "icons" / filename
        try:
            original = pygame.image.load(str(path)).convert_alpha()
            ICON_CACHE[key] = pygame.transform.smoothscale(original, (size, size))
        except (pygame.error, OSError) as exc:
            print(f"Icon load error: {filename}: {exc}")
            return None
    return ICON_CACHE[key]

EVENTS = [
    {"emoji": "📄", "label": "과제", "category": "academic", "color": (76, 126, 218), "weight": 20},
    {"emoji": "📝", "label": "시험", "category": "academic", "color": (213, 66, 67), "weight": 18},
    {"emoji": "📚", "label": "공부", "category": "academic", "color": (56, 153, 111), "weight": 17},
    {"emoji": "🏫", "label": "수업", "category": "academic", "color": (57, 143, 169), "weight": 15},
    {"emoji": "💗", "label": "사랑", "category": "romance", "color": (221, 94, 142), "weight": 15},
    {"emoji": "🎸", "label": "동아리", "category": "club", "color": (171, 100, 189), "weight": 15},
]
EVENT_BY_LABEL = {event["label"]: event for event in EVENTS}
ACADEMIC_NAMES = [e["label"] for e in EVENTS if e["category"] == "academic"]
SOCIAL_NAMES = [e["label"] for e in EVENTS if e["category"] != "academic"]
ALL_NAMES = [e["label"] for e in EVENTS]


def center_text(surface, font, message, color, cx, cy):
    img = font.render(str(message), True, color)
    surface.blit(img, img.get_rect(center=(int(cx), int(cy))))


def text_at(surface, font, message, color, x, y):
    surface.blit(font.render(str(message), True, color), (int(x), int(y)))


def wrapped_text(surface, font, message, color, x, y, max_width, line_height=24):
    """실제 글꼴의 픽셀 너비로 줄바꿈해 졸업 스크립트가 잘리지 않도록 함."""
    words = message.split(" ")
    line = ""
    for word in words:
        candidate = (line + " " + word).strip()
        if line and font.size(candidate)[0] > max_width:
            text_at(surface, font, line, color, x, y)
            y += line_height
            line = word
        else:
            line = candidate
    if line:
        text_at(surface, font, line, color, x, y)


def fitted_text(surface, message, color, x, y, max_width, size=18, min_size=13):
    """긴 한글 멘트가 게임 창 밖으로 나가지 않도록 글자 크기를 줄여 그린다."""
    message = str(message)
    for point_size in range(size, min_size - 1, -1):
        font = pygame.font.Font(font_name, point_size)
        if font.size(message)[0] <= max_width:
            surface.blit(font.render(message, True, color), (int(x), int(y)))
            return
    font = pygame.font.Font(font_name, min_size)
    while message and font.size(message + "…")[0] > max_width:
        message = message[:-1]
    surface.blit(font.render(message + "…", True, color), (int(x), int(y)))


def centered_fitted_text(surface, message, color, cx, cy, max_width, size=34):
    """제목이 긴 엔딩도 중앙 정렬을 유지한다."""
    for point_size in range(size, 21, -1):
        font = pygame.font.Font(font_name, point_size)
        if font.size(message)[0] <= max_width:
            return center_text(surface, font, message, color, cx, cy)
    return center_text(surface, pygame.font.Font(font_name, 21), message, color, cx, cy)


def draw_room(surface):
    # 기존 원룸 배경 유지
    surface.fill(WALL)
    floor_y = int(HEIGHT * 0.72)
    pygame.draw.rect(surface, FLOOR, (0, floor_y, WIDTH, HEIGHT - floor_y))
    for xx in range(0, WIDTH, 70):
        pygame.draw.line(surface, FLOOR_LINE, (xx, floor_y), (xx + 40, HEIGHT), 2)

    pygame.draw.rect(surface, (210, 210, 210), (70, 80, 180, 120), border_radius=8)
    pygame.draw.rect(surface, SKY, (78, 88, 164, 104), border_radius=6)
    pygame.draw.line(surface, (210, 210, 210), (160, 88), (160, 192), 4)
    pygame.draw.line(surface, (210, 210, 210), (78, 140), (242, 140), 4)
    for xx, yy, rr in [(110, 120, 16), (126, 112, 18), (145, 120, 15),
                       (195, 155, 14), (212, 148, 17), (228, 156, 13)]:
        pygame.draw.circle(surface, CLOUD, (xx, yy), rr)

    pygame.draw.rect(surface, BED_FRAME, (40, 420, 250, 110), border_radius=10)
    pygame.draw.rect(surface, BED_BLANKET, (55, 440, 220, 70), border_radius=10)
    pygame.draw.rect(surface, BED_PILLOW, (60, 435, 70, 30), border_radius=8)

    pygame.draw.rect(surface, DESK, (730, 420, 200, 24), border_radius=6)
    pygame.draw.rect(surface, DESK, (745, 444, 10, 90))
    pygame.draw.rect(surface, DESK, (905, 444, 10, 90))
    pygame.draw.rect(surface, MONITOR, (785, 345, 90, 55), border_radius=6)
    pygame.draw.rect(surface, (70, 90, 120), (792, 352, 76, 41), border_radius=4)
    pygame.draw.rect(surface, MONITOR, (825, 400, 10, 16))
    pygame.draw.rect(surface, MONITOR, (805, 414, 50, 8), border_radius=4)
    pygame.draw.rect(surface, CHAIR, (785, 470, 70, 18), border_radius=6)
    pygame.draw.rect(surface, CHAIR, (812, 488, 16, 48))
    pygame.draw.circle(surface, CHAIR, (795, 540), 8)
    pygame.draw.circle(surface, CHAIR, (845, 540), 8)

    pygame.draw.ellipse(surface, RUG, (335, 500, 330, 95))
    pygame.draw.rect(surface, (160, 120, 95), (310, 120, 110, 18), border_radius=4)
    pygame.draw.rect(surface, (220, 100, 100), (320, 90, 20, 30), border_radius=3)
    pygame.draw.rect(surface, (100, 160, 220), (350, 80, 20, 40), border_radius=3)
    pygame.draw.rect(surface, (120, 200, 140), (380, 95, 18, 25), border_radius=3)


def draw_student(surface, x, y, ticks):
    # 크림슨 후드, 일자 앞머리+세모 틈 — 앞서 함께 만든 외형 그대로
    y = int(y + math.sin(ticks * 0.004) * 4)
    pygame.draw.ellipse(surface, (155, 145, 165), (x - 55, y + 115, 110, 16))
    pygame.draw.rect(surface, PANTS, (x - 25, y + 60, 20, 48), border_radius=8)
    pygame.draw.rect(surface, PANTS, (x + 5, y + 60, 20, 48), border_radius=8)
    pygame.draw.ellipse(surface, SHOES, (x - 32, y + 101, 32, 15))
    pygame.draw.ellipse(surface, SHOES, (x + 1, y + 101, 32, 15))
    pygame.draw.ellipse(surface, CRIMSON, (x - 57, y + 8, 25, 65))
    pygame.draw.ellipse(surface, CRIMSON, (x + 32, y + 8, 25, 65))
    pygame.draw.circle(surface, SKIN, (x - 46, y + 65), 10)
    pygame.draw.circle(surface, SKIN, (x + 46, y + 65), 10)
    pygame.draw.rect(surface, CRIMSON, (x - 42, y - 2, 84, 81), border_radius=32)
    pygame.draw.rect(surface, DARK_CRIMSON, (x - 26, y + 40, 52, 28), border_radius=11)
    pygame.draw.rect(surface, LIGHT_CRIMSON, (x - 26, y + 40, 52, 28), width=2, border_radius=11)
    pygame.draw.ellipse(surface, CRIMSON, (x - 50, y - 108, 100, 110))
    pygame.draw.ellipse(surface, DARK_CRIMSON, (x - 40, y - 96, 80, 90))
    pygame.draw.ellipse(surface, SKIN, (x - 34, y - 88, 68, 79))

    hair_color = (65, 43, 38)
    pygame.draw.ellipse(surface, hair_color, (x - 32, y - 96, 64, 34))
    pygame.draw.rect(surface, hair_color, (x - 30, y - 82, 60, 21))
    for dx in (-18, 0, 18):
        pygame.draw.polygon(surface, SKIN, [(x + dx - 4, y - 61),
                                           (x + dx, y - 71),
                                           (x + dx + 4, y - 61)])
    pygame.draw.ellipse(surface, (45, 34, 40), (x - 19, y - 55, 10, 14))
    pygame.draw.ellipse(surface, (45, 34, 40), (x + 9, y - 55, 10, 14))
    pygame.draw.circle(surface, WHITE, (x - 14, y - 51), 2)
    pygame.draw.circle(surface, WHITE, (x + 14, y - 51), 2)
    pygame.draw.ellipse(surface, (234, 166, 166), (x - 29, y - 37, 19, 11))
    pygame.draw.ellipse(surface, (234, 166, 166), (x + 10, y - 37, 19, 11))
    pygame.draw.arc(surface, (172, 104, 112),
                    (x - 8, y - 32, 16, 11), math.pi, 2 * math.pi, 2)
    pygame.draw.line(surface, (244, 217, 206), (x - 12, y + 2), (x - 15, y + 34), 3)
    pygame.draw.line(surface, (244, 217, 206), (x + 12, y + 2), (x + 15, y + 34), 3)
    pygame.draw.circle(surface, (244, 217, 206), (x - 15, y + 34), 3)
    pygame.draw.circle(surface, (244, 217, 206), (x + 15, y + 34), 3)


def draw_target(surface, ticks):
    pulse = 2 * math.sin(ticks / 145)
    pygame.draw.circle(surface, (242, 233, 224), TARGET, int(46 + pulse))
    pygame.draw.circle(surface, CRIMSON, TARGET, int(43 + pulse), 5)
    pygame.draw.circle(surface, WHITE, TARGET, 29, 3)
    center_text(surface, TINY_FONT, "CLICK", DARK_CRIMSON, TARGET[0], TARGET[1])


def get_note_start():
    # 아래쪽에서는 절대로 노트가 나타나지 않음
    side = random.choice(("top", "left", "right"))
    if side == "top":
        return (random.randint(90, WIDTH - 90), -75)
    if side == "left":
        return (-75, random.randint(120, 475))
    return (WIDTH + 75, random.randint(120, 475))


def build_random_notes(year, exam=False, social_schedule=None):
    """평화로운 BGM과 별개로 불규칙한 학업 노트 도착 시각을 예약한다.

    일반 학기에는 하트/기타가 뜬 직후 약 0.9초 동안 새 학업 노트가
    판정선에 도달하지 않게 하여 마우스를 옮길 기회를 마련한다.
    시험 기간은 기존대로 학업만 집중적으로 등장한다.
    """
    base_gap, flight, _, _, _, max_window = DIFFICULTY[year]
    if exam:
        period_ms = EXAM_MS
        base_gap = round(base_gap * 0.80)
        flight = round(flight * 0.84)
        min_gap = max(MIN_GAP_MS[year], max_window * 2 + 35)
        arrival = flight + random.randint(220, 480)
    else:
        period_ms = PHASE_MS
        min_gap = MIN_GAP_MS[year]
        arrival = flight + random.randint(500, 900)

    # 실제 등장 시각 자체를 옮기는 것이 아니라 '판정선 도착 시각'을 조정한다.
    # 아이콘을 클릭하러 갔다가 다시 중앙으로 돌아올 짧은 틈이 생긴다.
    social_windows = []
    if not exam and social_schedule:
        social_windows = [
            (e["spawn"] - SOCIAL_BREATH_BEFORE_MS,
             e["spawn"] + SOCIAL_BREATH_AFTER_MS)
            for e in social_schedule
        ]

    def clear_social_window(time):
        for start, end in social_windows:
            if start <= time <= end:
                time = end + random.randint(80, 170)
        return time

    last_arrival = period_ms - max_window - 250
    arrival_times = []
    while arrival <= last_arrival:
        mode = random.choices(
            ("normal", "rush", "quiet"),
            weights=(37, 58, 5) if exam else (50, 32, 18),
            k=1,
        )[0]
        steps = random.randint(2, 5) if mode == "rush" else random.randint(1, 3)
        for _ in range(steps):
            arrival = clear_social_window(arrival)
            if arrival > last_arrival:
                break
            # 이전 노트와 너무 가까워지지 않게 판정 시각을 다시 확인한다.
            if arrival_times and arrival < arrival_times[-1] + min_gap:
                arrival = clear_social_window(arrival_times[-1] + min_gap)
                if arrival > last_arrival:
                    break
            arrival_times.append(round(arrival))
            if mode == "rush":
                multiplier = random.uniform(0.57, 0.85)
            elif mode == "quiet":
                multiplier = random.uniform(1.65, 2.6)
            else:
                multiplier = random.uniform(0.85, 1.35)
            gap = max(min_gap, round(base_gap * multiplier))
            arrival += gap
        if random.random() < (0.05 if exam else 0.15):
            arrival += random.randint(220, 480) if exam else random.randint(250, 750)

    if exam:
        exam_events = [EVENT_BY_LABEL[n] for n in ("과제", "시험", "공부")]
        chosen = random.choices(exam_events, weights=[36, 39, 25], k=len(arrival_times))
    else:
        # 사방에서 날아오는 노트는 학업 4종만 사용한다.
        academic_events = [EVENT_BY_LABEL[n] for n in ACADEMIC_NAMES]
        chosen = random.choices(
            academic_events, weights=[e["weight"] for e in academic_events],
            k=len(arrival_times),
        )

    return [
        {
            "emoji": event["emoji"],
            "label": event["label"],
            "category": event["category"],
            "color": event["color"],
            "start": get_note_start(),
            "arrive": arrive,
            "spawn": arrive - flight,
            "flight": flight,
        }
        for arrive, event in zip(arrival_times, chosen)
    ]


def draw_note(surface, note, elapsed):
    p = max(0.0, min(1.0, (elapsed - note["spawn"]) / note["flight"]))
    sx, sy = note["start"]
    xx = round(sx + (TARGET[0] - sx) * p)
    yy = round(sy + (TARGET[1] - sy) * p)
    rect = pygame.Rect(xx - 31, yy - 31, 62, 62)
    pygame.draw.rect(surface, note["color"], rect, border_radius=18)
    pygame.draw.rect(surface, WHITE, rect, 3, border_radius=18)
    icon_img = get_event_icon(note["emoji"], 37)
    if icon_img is not None:
        surface.blit(icon_img, icon_img.get_rect(center=(xx, yy - 6)))
    label_img = TINY_FONT.render(note["label"], True, WHITE)
    surface.blit(label_img, label_img.get_rect(center=(xx, yy + 22)))



def build_social_events(year):
    """평범한 학기 중 사랑·동아리 이벤트를 불규칙한 시각에 예약한다.

    학업 노트와는 별도 타임라인. 시험 기간에는 발생하지 않는다.
    만료 전에 클릭할 수 있도록 학기 종료 적어도 4.2초 전까지만 등장.
    """
    schedule = []
    at = random.randint(1400, 2500)
    latest = PHASE_MS - SOCIAL_LIFETIME_RANGE[1] - 220
    low, high = SOCIAL_GAPS[year]
    count = {"사랑": 0, "동아리": 0}
    while at <= latest:
        # 두 이벤트가 어느 한쪽에 편중되지 않도록 2개 이상 차이 나면 균형을 잡는다.
        if count["사랑"] >= count["동아리"] + 2:
            label = "동아리"
        elif count["동아리"] >= count["사랑"] + 2:
            label = "사랑"
        else:
            label = random.choice(("사랑", "동아리"))
        count[label] += 1
        event = EVENT_BY_LABEL[label]
        life = random.randint(*SOCIAL_LIFETIME_RANGE)
        schedule.append({
            "label": label, "emoji": event["emoji"], "color": event["color"],
            "spawn": at, "expire": at + life, "lifetime": life,
        })
        at += random.randint(low, high)
    return schedule


def choose_social_position(existing, academic_notes=None, elapsed=0):
    """HUD, 캐릭터, 콤보, 중앙 타깃, 다른 이벤트를 피해 무작위 위치 선택."""
    academic_notes = academic_notes or []
    for _ in range(150):
        x, y = random.randint(90, WIDTH - 90), random.randint(161, 485)
        if 412 <= x <= 586 and 255 <= y <= 508:  # 후드 캐릭터
            continue
        if 530 <= x <= 712 and 332 <= y <= 461:  # 콤보 패널
            continue
        if math.dist((x, y), TARGET) < 140:       # 중앙 판정원
            continue
        if any(math.dist((x, y), e["pos"]) < 115 for e in existing):
            continue
        # 탄생 순간 학업 노트의 위를 덮지 않게 한다.
        overlapping = False
        for note in academic_notes:
            p = max(0, min(1, (elapsed - note["spawn"]) / note["flight"]))
            sx, sy = note["start"]
            nx = sx + (TARGET[0] - sx) * p
            ny = sy + (TARGET[1] - sy) * p
            if math.dist((x, y), (nx, ny)) < 92:
                overlapping = True
                break
        if overlapping:
            continue
        return (x, y)
    # 후보가 적은 상황에서도 항상 클릭 가능한 방 안의 위치를 사용한다.
    candidates = [(155, 260), (845, 260), (165, 390), (835, 450), (350, 195)]
    return max(candidates, key=lambda pos: min(
        [math.dist(pos, other["pos"]) for other in existing] + [500]
    ))


def draw_social_event(surface, event, elapsed, ticks):
    """하트/기타가 있는 고정 아이콘. 바깥의 작은 막대로 남은 시간 표시."""
    x, y = event["pos"]
    float_y = round(math.sin(ticks / 330 + x / 65) * 3)
    center = (x, y + float_y)
    color = event["color"]
    pygame.draw.circle(surface, (250, 240, 236), center, 45)
    pygame.draw.circle(surface, color, center, 40)
    pygame.draw.circle(surface, WHITE, center, 40, 3)
    icon_img = get_event_icon(event["emoji"], 49)
    if icon_img is not None:
        surface.blit(icon_img, icon_img.get_rect(center=(x, y + float_y - 10)))
    center_text(surface, TINY_FONT, event["label"], WHITE, x, y + float_y + 21)
    remaining = max(0.0, min(1.0, (event["expire"] - elapsed) / event["lifetime"]))
    bar = pygame.Rect(x - 36, y + 48, 72, 6)
    pygame.draw.rect(surface, (232, 220, 216), bar, border_radius=3)
    if remaining > 0:
        fill = pygame.Rect(bar.x, bar.y, max(1, round(bar.width * remaining)), bar.height)
        pygame.draw.rect(surface, color, fill, border_radius=3)


def grade_details(judgments, total):
    """학업 노트 실수 중 최대 3개를 학점 감점에서만 제외한다.

    실제 판정 카운트와 체력/콤보/사회 활동은 절대 수정하지 않는다.
    가장 큰 감점부터 유예해 작은 실수 여러 개 때문에 과도하게
    학점이 내려가지 않도록 한다 (MISS -> OK -> GOOD 순서).
    """
    remaining = {name: int(judgments.get(name, 0)) for name in PENALTY_UNITS}
    waived = {name: 0 for name in PENALTY_UNITS}
    budget = GRADE_GRACE_MISTAKES
    for name in ("MISS", "OK", "GOOD"):
        count = min(budget, remaining[name])
        remaining[name] -= count
        waived[name] = count
        budget -= count
    waived_count = GRADE_GRACE_MISTAKES - budget
    raw_units = sum(int(judgments.get(name, 0)) * units
                    for name, units in PENALTY_UNITS.items())
    graded_units = sum(remaining[name] * units
                       for name, units in PENALTY_UNITS.items())
    return {
        "waived_count": waived_count,
        "waived": waived,
        "remaining": remaining,
        "raw_units": raw_units,
        "graded_units": graded_units,
        "effective_misses_after_grace": graded_units / 3,
    }


def letter_grade(judgments, total):
    """A+는 전부 PERFECT, A는 학업 실수 3회 유예까지 허용.

    3회 초과분에는 이전의 GOOD/OK/MISS별 감점과 비율제를 적용한다.
    F와 D는 소규모 학기에서 실수 1개 때문에 바로 뜨지 않도록
    유예 후 MISS 최소 개수 기준도 둔다.
    """
    if total <= 0:
        return "-"
    if judgments.get("PERFECT", 0) == total:
        return "A+"
    details = grade_details(judgments, total)
    left = details["remaining"]
    miss = left["MISS"]
    ratio = details["graded_units"] / (3 * total)
    miss_ratio = miss / total

    if (miss >= 4 and miss_ratio >= F_MISS_RATIO) or ratio >= F_PENALTY_RATIO:
        return "F"
    if (miss >= 2 and miss_ratio >= D_MISS_RATIO) or ratio >= D_PENALTY_RATIO:
        return "D"
    if miss or left["OK"] or ratio >= C_PENALTY_RATIO:
        return "C"
    if left["GOOD"]:
        return "B"
    return "A"


# 학기 결산에서 등장하는 센스 있는 문구. 사랑/동아리는 클릭 성공률만 계산한다.
def club_outcome(hits, total):
    if total <= 0:
        return ("조용한 학기", "이번 학기엔 동아리와 마주칠 기회가 없었다.")
    rate = hits / total
    if hits == 0:
        return ("고독한 대학생", "동방의 위치는 끝내 미스터리로 남았다.")
    if rate < 0.25:
        return ("유령 부원", "단톡방에는 있었지만 존재감은 로그아웃 상태였다.")
    if rate < 0.50:
        return ("어색한 동기", "아는 얼굴은 늘었다. 이름은... 다음 학기에 외우자.")
    if rate < 0.75:
        return ("괜찮은 대학 생활", "수업이 끝나도 집에 바로 가지 않을 이유가 생겼다.")
    if rate < 0.90:
        return ("인싸의 삶", "학교에서 아는 사람을 피해 다니기가 더 어려워졌다.")
    return ("동방의 지박령", "등록금은 학교에 냈는데, 정작 집은 동방에 있었다.")


def romance_outcome(hits, total):
    if total <= 0:
        return ("아직 시작 전", "이번 학기엔 사랑이 문을 두드리지 않았다.")
    rate = hits / total
    if hits == 0:
        return ("모태솔로의 길", "캠퍼스에도 봄은 왔다. 나한테만 안 왔을 뿐.")
    if rate < 0.25:
        return ("혼자만의 로맨스", "짝사랑도 사랑이라면, 나도 연애를 한 셈 아닐까?")
    if rate < 0.50:
        return ("아슬아슬한 썸", "분명 썸인 줄 알았는데, 알고 보니 나 혼자 탄 거였다.")
    if rate < 0.75:
        return ("설렘의 시작", "과제 마감보다 그 사람의 답장을 더 기다렸다.")
    if rate < 0.90:
        return ("달콤한 연애", "바쁜 시간표 사이에도 그 사람을 위한 빈칸은 있었다.")
    return ("캠퍼스 로맨스", "학점표엔 나오지 않는 A+를 받았다. 바로 사랑!")


def club_comment(hits, total):
    return club_outcome(hits, total)[1]


def romance_comment(hits, total):
    return romance_outcome(hits, total)[1]


# 학점(상·중·하) × 연애(낮음·보통·높음) × 동아리(낮음·보통·높음):
# 서로 다른 27개 졸업 엔딩. 추가로 완벽한 8학기 등 숨겨진 엔딩도 존재한다.
GRADUATION_ENDINGS = {
    # 학점 상위권
    ("high", "low", "low"): (
        "전설의 도서관 망령",
        "4년 동안 과제와 시험을 완벽하게 해냈다. 교수님들은 네 이름을 기억하지만, 동기들은 네 얼굴을 잘 모른다. 그래도 졸업장은 유난히 빛난다."),
    ("high", "low", "mid"): (
        "공부하다 가끔 놀러 나갔다",
        "시험 범위는 외웠고 동아리 사람들의 이름도 제법 외웠다. 사랑은 다음 학기로 미뤄 두었는데, 어느새 마지막 학기가 끝났다."),
    ("high", "low", "high"): (
        "도서관과 동방의 이중생활",
        "낮에는 과제, 밤에는 동아리. 두 곳의 출석률만큼은 누구에게도 지지 않았다. 연애는 못 했어도 함께할 친구는 넘쳐났다."),
    ("high", "mid", "low"): (
        "제출 버튼이 먼저였다",
        "설렘은 분명 있었다. 하지만 답장을 보낼 때쯤이면 언제나 과제 마감 알림이 울렸다. 그 덕분에 성적표는 아주 훌륭하다."),
    ("high", "mid", "mid"): (
        "균형 잡힌 우등생",
        "시험도 챙기고 가끔은 친구와 웃고, 누군가에게 마음을 내주기도 했다. 대단한 사건이 없었기에 오히려 소중한 4년이었다."),
    ("high", "mid", "high"): (
        "동방에서 시험공부를",
        "동아리에 가서 공부하고, 공부하다가 친구들과 웃었다. 연애는 조금 애매했지만 대학 생활이 외로울 틈은 없었다."),
    ("high", "high", "low"): (
        "학점도 사랑도 A+",
        "성적표도 훌륭했고 사랑도 놓치지 않았다. 다만 졸업식 단체사진에서 모르는 얼굴이 좀 많았다. 괜찮아, 옆에는 가장 소중한 사람이 있으니까."),
    ("high", "high", "mid"): (
        "시간표의 비밀 빈칸",
        "수업과 과제 사이에 데이트를 넣고, 친구들과의 약속도 빼먹지 않았다. 시간표를 짠 사람이 누구인지 궁금할 정도로 알찬 4년이었다."),
    ("high", "high", "high"): (
        "캠퍼스 라이프 올클리어",
        "학점도 사랑도 인간관계도 놓치지 않았다. 이 정도면 인생에 치트키를 쓴 게 아닐까? 졸업식 날, 네 주위는 축하해 주는 사람들로 가득했다."),
    # 학점 중위권
    ("mid", "low", "low"): (
        "조용히 살아남은 대학생",
        "대단한 사랑도 요란한 모임도 없었지만, 수많은 과제와 시험을 견뎌 냈다. 조금 심심했어도 네 4년은 분명 진짜였다."),
    ("mid", "low", "mid"): (
        "점심 약속은 있었다",
        "사랑 이야기는 남의 일 같았지만, 강의가 끝나면 같이 밥 먹을 친구는 있었다. 학점표와 학식 메뉴를 함께 고민하던 날들이 남았다."),
    ("mid", "low", "high"): (
        "동방이 제2의 전공",
        "시험 점수는 평범했지만 동아리에 관한 문제라면 자신 있었다. 연애는 못 했어도 졸업식 뒤풀이 참석자는 누구보다 많았다."),
    ("mid", "mid", "low"): (
        "미완성 로맨스의 주인공",
        "전공 공부도, 설레는 마음도 적당히 어려웠다. 몇 번의 어색한 썸이 지나갔고, 네 청춘에는 아직 다음 화가 남아 있다."),
    ("mid", "mid", "mid"): (
        "평균값에 담긴 청춘",
        "성적도 사랑도 인간관계도 조금씩 성공하고 조금씩 실패했다. 그런데 돌이켜 보면 이상하게 좋은 기억이 더 많이 남는다."),
    ("mid", "mid", "high"): (
        "썸은 놓쳤지만 합주는 성공",
        "사랑의 타이밍은 몇 번 놓쳤다. 그래도 친구들과 밤새 떠들며 만든 추억은 절대 MISS가 아니었다. 졸업 후에도 연락할 사람이 많다."),
    ("mid", "high", "low"): (
        "과제보다 기다려진 답장",
        "학점은 무난했고 사랑은 빛났다. 친구는 많지 않았지만 둘이서 걷던 캠퍼스 길만큼은 지도 없이도 찾아갈 수 있다."),
    ("mid", "high", "mid"): (
        "성적표 밖의 우등생",
        "학점이 전부는 아니었다. 함께 웃는 친구들이 있었고, 바쁜 와중에도 좋아하는 사람을 만났다. 꽤 괜찮은 대학 생활이었다."),
    ("mid", "high", "high"): (
        "성적표보다 두꺼운 앨범",
        "학점은 조금 아쉽지만 사진첩에는 빈 페이지가 없었다. 졸업식에는 친구와 연인이 찾아왔고, 성적표는 잠깐 가방 속에 넣어 두었다."),
    # 학점 하위권
    ("low", "low", "low"): (
        "졸업장 하나는 남았다",
        "성적표는 구겨졌고 달력에는 밀린 일정이 가득했다. 하지만 8학기를 지나 결국 졸업장까지 도착했다. 오늘만큼은 살아남은 자신을 칭찬하자."),
    ("low", "low", "mid"): (
        "재수강 동지들",
        "공부가 안 풀리는 날에는 친구들과 한숨을 나눴다. 사랑의 기척은 없었지만 적어도 혼자 도서관에 앉아 있진 않았다."),
    ("low", "low", "high"): (
        "동방에서 졸업하다",
        "강의실은 낯설어도 동방 소파는 내 집 같았다. 학점이 조금 위험했지만 친구들이 졸업을 함께 축하해 줬다. 정작 전공 책은 어디 뒀더라?"),
    ("low", "mid", "low"): (
        "답장 기다리다 놓친 과제",
        "사랑도 공부도 손에 잡힐 듯 잡히지 않았다. 때로는 달콤했고 때로는 씁쓸했다. 그래도 그 서툰 시간들이 모여 4년이 됐다."),
    ("low", "mid", "mid"): (
        "청춘은 채점할 수 없다",
        "학점은 기대에 못 미쳤다. 그래도 썸도 타 보고 친구들과 웃기도 했다. 시험지에 적히지 않은 답들을 4년 동안 조금씩 배웠다."),
    ("low", "mid", "high"): (
        "기타 줄은 갈았지만 학점은",
        "동아리에는 빠짐없이 갔지만 시험 대비는 자주 놓쳤다. 사랑 이야기는 아직 미완성. 그래도 학교에 남은 네 흔적은 결코 작지 않다."),
    ("low", "high", "low"): (
        "사랑이 전공이었습니다",
        "중간고사보다 기념일을 더 잘 기억했고, 학점 대신 설렘을 수집했다. 성적표는 아쉽지만 사랑 이야기는 누구보다 풍성하다."),
    ("low", "high", "mid"): (
        "성적표보다 사진첩",
        "시험에는 자주 졌지만 사랑에는 꽤 자주 웃었다. 친구들과 찍은 사진도 차곡차곡 남았다. 졸업 후 펼쳐 볼 것은 성적표보다 앨범일지도 모른다."),
    ("low", "high", "high"): (
        "낭만은 학점순이 아니잖아요",
        "성적표는 조금 초라했지만 졸업식에는 누구보다 많은 사람들이 찾아왔다. 네 대학 생활은 성적표보다 사진첩에 더 많이 남았다."),
}


def graduation_ending(gpa, club_hits, club_total, romance_hits, romance_total, records=None):
    """실제 8학기 학점과 사랑/동아리 클릭 성공률로 엔딩 선정."""
    club_rate = club_hits / club_total if club_total else 0
    love_rate = romance_hits / romance_total if romance_total else 0
    grades = [r.get("grade", "-") for r in (records or [])]
    if len(grades) == 8 and all(grade == "A+" for grade in grades):
        if love_rate >= 0.75 and club_rate >= 0.75:
            return ("8학기 올 퍼펙트, 인생도 만점",
                    "학점표에는 A+만 여덟 개. 동방과 사랑도 포기하지 않았다. 대학 생활의 모든 버튼을 정확히 눌렀다. 이제는 한 박자 쉬어도 괜찮다.")
        return ("8학기 올 퍼펙트의 전설",
                "성적표에 A+ 여덟 개가 빼곡하다. 미처 못 챙긴 만남이 있었을지라도, 4년간 공부에 쏟은 노력만큼은 누구도 부정할 수 없다.")
    school = "high" if gpa >= 3.5 else "mid" if gpa >= 2.0 else "low"
    love = "high" if love_rate >= 0.75 else "mid" if love_rate >= 0.25 else "low"
    club = "high" if club_rate >= 0.75 else "mid" if club_rate >= 0.25 else "low"
    return GRADUATION_ENDINGS[(school, love, club)]


def load_background_music():
    """main.py와 같은 폴더의 music.ogg 또는 music.mp3를 불러온다.

    파일이 없으면 음악 없이 진행한다. 노트 타이밍은 음악에 의존하지 않는다.
    """
    if not pygame.mixer.get_init():
        return None
    folder = Path(__file__).resolve().parent
    for filename in MUSIC_CANDIDATES:
        path = folder / filename
        if not path.is_file():
            continue
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(MUSIC_VOLUME)
            return filename
        except (pygame.error, OSError) as exc:
            print(f"음악 파일을 열 수 없습니다 ({filename}): {exc}")
    return None


class Game:
    def __init__(self):
        self.music_name = load_background_music()
        self.sound_on = bool(self.music_name)
        self.music_started = False
        self.music_paused = False
        self.state = "ready"
        self.running = True
        self.reset_data()

    def reset_data(self):
        self.year = 1
        self.semester = 1
        self.health = START_HEALTH
        self.score = 0
        self.combo = 0
        self.best_combo = 0
        self.records = []
        self.phase_start = 0
        self.segment = "regular"
        self.exam_intro_at = 0
        self.elapsed = 0
        self.planned = []
        self.spawn_index = 0
        self.active = []
        self.social_planned = []
        self.social_index = 0
        self.social_active = []
        self.social_feedback = None
        self.hits = {name: 0 for name in ALL_NAMES}
        self.misses = {name: 0 for name in ALL_NAMES}
        self.penalties = {name: 0 for name in ACADEMIC_NAMES}
        self.judgments = {name: {j: 0 for j in PENALTY_UNITS} for name in ACADEMIC_NAMES}
        self.totals = {name: 0 for name in ALL_NAMES}
        self.feedback = ""
        self.feedback_color = WHITE
        self.feedback_at = -999999
        self.ending_page = 0

    def new_game(self, ticks):
        # 새로운 인생은 노래 처음부터 시작
        self.stop_audio()
        self.reset_data()
        self.begin_semester(ticks)

    def stop_audio(self):
        if self.music_name:
            pygame.mixer.music.stop()
        self.music_started = False
        self.music_paused = False

    def pause_audio(self):
        # 학기 결산 중에는 노래를 멈췄다가 다음 학기에 이어 재생
        if self.music_name and self.music_started and not self.music_paused:
            pygame.mixer.music.pause()
            self.music_paused = True

    def begin_semester(self, ticks):
        self.state = "playing"
        self.segment = "regular"
        if self.music_name:
            try:
                pygame.mixer.music.set_volume(MUSIC_VOLUME if self.sound_on else 0)
                if not self.music_started:
                    # 노래가 끝나면 다시 처음부터 반복. 노트는 무작위 등장.
                    pygame.mixer.music.play(-1)
                    self.music_started = True
                    self.music_paused = False
                elif self.music_paused:
                    # 학기 결산 전 재생 위치에서 이어 듣기
                    pygame.mixer.music.unpause()
                    self.music_paused = False
            except pygame.error as exc:
                print(f"음악 재생 오류: {exc}")
                self.music_name = None
                self.music_started = False
                self.music_paused = False
        # 학기 시작 시점을 기준으로 타이머와 무작위 노트 스케줄 계산
        self.phase_start = pygame.time.get_ticks()
        self.elapsed = 0
        self.active.clear()
        # 사회 이벤트의 출현 시각을 먼저 정해, 노트가 도착하는 시각에 여유를 배치.
        self.social_planned = build_social_events(self.year)
        self.planned = build_random_notes(
            self.year, exam=False, social_schedule=self.social_planned
        )
        self.spawn_index = 0
        self.social_index = 0
        self.social_active.clear()
        self.social_feedback = None
        self.hits = {name: 0 for name in ALL_NAMES}
        self.misses = {name: 0 for name in ALL_NAMES}
        self.penalties = {name: 0 for name in ACADEMIC_NAMES}
        self.judgments = {name: {j: 0 for j in PENALTY_UNITS} for name in ACADEMIC_NAMES}
        self.totals = {name: 0 for name in ALL_NAMES}
        for note in self.planned:
            self.totals[note["label"]] += 1
        for event in self.social_planned:
            self.totals[event["label"]] += 1
        self.feedback = ""
        self.feedback_at = -999999

    def set_feedback(self, message, color, ticks):
        self.feedback = message
        self.feedback_color = color
        self.feedback_at = ticks

    def record_judgment(self, label, judgment):
        """학업 노트만 5단계 판정. GOOD 3번 = MISS 1번."""
        assert label in ACADEMIC_NAMES, "사랑·동아리에는 5단계 판정을 사용하지 않습니다."
        self.judgments[label][judgment] += 1
        self.penalties[label] += PENALTY_UNITS[judgment]
        if judgment == "MISS":
            self.misses[label] += 1
        else:
            self.hits[label] += 1

    def record_social_result(self, label, success):
        """사랑·동아리는 성공/실패만 기록. 학점·체력·점수·콤보 불변."""
        assert label in SOCIAL_NAMES
        if success:
            self.hits[label] += 1
        else:
            self.misses[label] += 1

    def miss(self, note, ticks):
        self.record_judgment(note["label"], "MISS")
        damage = MISS_DAMAGE_CLASS if note["label"] == "수업" else MISS_DAMAGE_NORMAL
        self.health = max(0, self.health - damage)
        self.combo = 0
        self.set_feedback(f"MISS!  -체력 {damage}", (204, 48, 76), ticks)

    def click_social(self, pos, ticks):
        """하트·기타는 나타나 있는 동안 클릭하면 성공. 점수/콤보/체력 불변."""
        candidates = [(math.dist(pos, e["pos"]), e) for e in self.social_active]
        if not candidates:
            return False
        delta, event = min(candidates, key=lambda item: item[0])
        if delta > SOCIAL_CLICK_RADIUS:
            return False

        self.social_active.remove(event)
        age = max(0, ticks - self.phase_start - event["spawn"])
        success = age < event["lifetime"]
        self.record_social_result(event["label"], success)
        self.social_feedback = {
            "text": f"{event['label']} {'성공!' if success else '실패!'}",
            "pos": event["pos"], "color": event["color"], "ticks": ticks,
        }
        return True

    def update_social(self, ticks):
        """랜덤 발생/3~4초 후 미클릭을 실패로 집계."""
        if self.segment != "regular":
            return
        while (self.social_index < len(self.social_planned)
               and self.social_planned[self.social_index]["spawn"] <= self.elapsed):
            event = self.social_planned[self.social_index].copy()
            event["pos"] = choose_social_position(self.social_active, self.active, self.elapsed)
            self.social_active.append(event)
            self.social_index += 1
        for event in self.social_active[:]:
            if self.elapsed >= event["expire"]:
                self.social_active.remove(event)
                self.record_social_result(event["label"], False)
                # 자동 만료는 학업 체력/학점/점수/콤보에 영향을 주지 않음.

    def flush_social(self):
        """학기 전환 시 남은 사회 이벤트를 중복 없이 실패 처리."""
        for event in self.social_active:
            self.record_social_result(event["label"], False)
        self.social_active.clear()
        for event in self.social_planned[self.social_index:]:
            self.record_social_result(event["label"], False)
        self.social_index = len(self.social_planned)

    def click_target(self, pos, ticks):
        if math.dist(pos, TARGET) > TARGET_RADIUS:
            return
        elapsed = ticks - self.phase_start
        _, _, perfect, great, good, okay = DIFFICULTY[self.year]
        candidates = [(abs(elapsed - n["arrive"]), n) for n in self.active]
        if candidates:
            delta, note = min(candidates, key=lambda p: p[0])
        else:
            delta, note = float("inf"), None

        if note is None or delta > okay:
            self.health = max(0, self.health - WRONG_CLICK_DAMAGE)
            self.combo = 0
            self.set_feedback("헛클릭!  -체력", (194, 83, 100), ticks)
            return

        self.active.remove(note)
        if delta <= perfect:
            judgment, points, color = "PERFECT", 300, (41, 158, 97)
        elif delta <= great:
            judgment, points, color = "GREAT", 240, (32, 146, 153)
        elif delta <= good:
            judgment, points, color = "GOOD", 150, (52, 123, 196)
        else:
            judgment, points, color = "OK", 60, (171, 110, 30)
        self.record_judgment(note["label"], judgment)
        self.score += points
        # PERFECT/GREAT만 콤보로 인정한다. GOOD/OK는 적중 점수만 얻고 콤보 초기화.
        if judgment in ("PERFECT", "GREAT"):
            self.combo += 1
            self.best_combo = max(self.best_combo, self.combo)
        else:
            self.combo = 0
        # 체력 회복도 PERFECT/GREAT 3콤보부터 성공할 때에만 적용한다.
        heal = COMBO_HEAL_AMOUNT if self.combo >= COMBO_HEAL_START else 0
        healed = min(heal, START_HEALTH - self.health)
        self.health += healed
        message = f"{judgment}!" + (f"  체력 +{healed}" if healed else "")
        self.set_feedback(message, color, ticks)

    def start_exam_intro(self, ticks):
        # 정규 학기 노트의 마지막 판정까지 정리하고 잠깐 화면을 어둡게 한다.
        for note in self.active:
            self.miss(note, ticks)
        self.active.clear()
        self.flush_social()
        self.exam_intro_at = ticks
        if self.health <= 0:
            self.state = "gameover"
            self.stop_audio()
        else:
            self.state = "exam_intro"

    def begin_exam(self, ticks):
        # 이전 학기 통계는 보존한 채 시험 기간 노트를 추가 집계한다.
        self.state = "playing"
        self.segment = "exam"
        self.phase_start = ticks
        self.elapsed = 0
        self.planned = build_random_notes(self.year, exam=True)
        self.spawn_index = 0
        self.active.clear()
        for note in self.planned:
            self.totals[note["label"]] += 1
        self.feedback = ""
        self.feedback_at = -999999

    def finish_semester(self):
        # 학기 마지막까지 남은 노트도 MISS로 집계 (중복 집계 방지)
        for note in self.active:
            self.record_judgment(note["label"], "MISS")
        self.active.clear()
        for note in self.planned[self.spawn_index:]:
            self.record_judgment(note["label"], "MISS")
        self.spawn_index = len(self.planned)
        self.flush_social()

        academic_total = sum(self.totals[k] for k in ACADEMIC_NAMES)
        academic_misses = sum(self.misses[k] for k in ACADEMIC_NAMES)
        academic_loss_units = sum(self.penalties[k] for k in ACADEMIC_NAMES)
        effective_misses = academic_loss_units / 3
        # 학업은 감점 환산, 사랑/동아리는 클릭 성공 개수만 사용.
        # 사회 이벤트의 성공/실패는 학점 및 학업 감점에 합산하지 않는다.
        academic_judgments = {
            j: sum(self.judgments[name][j] for name in ACADEMIC_NAMES)
            for j in PENALTY_UNITS
        }
        grace = grade_details(academic_judgments, academic_total)
        record = {
            "year": self.year,
            "semester": self.semester,
            "totals": self.totals.copy(),
            "hits": self.hits.copy(),
            "misses": self.misses.copy(),
            "judgments": {name: counts.copy() for name, counts in self.judgments.items()},
            "penalties": self.penalties.copy(),
            "social_results": {
                name: {"success": self.hits[name], "failure": self.misses[name],
                       "total": self.totals[name]}
                for name in SOCIAL_NAMES
            },
            "academic_total": academic_total,
            "academic_misses": academic_misses,
            "academic_judgments": academic_judgments,
            "academic_effective_misses": effective_misses,
            "academic_grace_used": grace["waived_count"],
            "academic_graded_effective_misses": grace["effective_misses_after_grace"],
            "grade": letter_grade(academic_judgments, academic_total),
        }
        self.records.append(record)
        self.pause_audio()
        self.state = "report"  # 시간은 멈추고 플레이어가 넘길 때까지 기다림

    def next_semester(self, ticks):
        if self.semester == 2:
            self.year += 1
            self.semester = 1
        else:
            self.semester += 1

        if self.year > 4:
            self.stop_audio()
            self.state = "ending"
            self.ending_page = 0
        else:
            # 학점 F를 받은 경우는 방학 회복 대신 체력 20으로 시작.
            previous_grade = self.records[-1]["grade"]
            if previous_grade == "F":
                self.health = F_NEXT_HEALTH
            else:
                self.health = min(START_HEALTH, self.health + SEMESTER_RECOVERY)
            self.begin_semester(ticks)

    def handle_event(self, event, ticks):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.state == "rules":
                self.state = "ready"
            else:
                self.running = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
            self.sound_on = not self.sound_on
            if self.music_name:
                pygame.mixer.music.set_volume(MUSIC_VOLUME if self.sound_on else 0)
            return

        key = event.type == pygame.KEYDOWN
        click = event.type == pygame.MOUSEBUTTONDOWN and event.button == 1

        if self.state == "ready":
            if (key and event.key == pygame.K_h) or (click and RULES_BUTTON.collidepoint(event.pos)):
                self.state = "rules"
            elif key or click:
                self.new_game(ticks)
        elif self.state == "rules":
            if (click and RULES_BACK_BUTTON.collidepoint(event.pos)) or (key and event.key in (pygame.K_BACKSPACE, pygame.K_RETURN, pygame.K_h)):
                self.state = "ready"
        elif self.state == "playing" and click:
            if not self.click_social(event.pos, ticks):
                self.click_target(event.pos, ticks)
        elif self.state == "report" and (key or click):
            self.next_semester(ticks)
        elif self.state == "gameover" and (key or click):
            self.new_game(ticks)
        elif self.state == "ending":
            if key and event.key == pygame.K_r:
                self.state = "ready"
                self.reset_data()
            elif key and event.key == pygame.K_LEFT:
                self.ending_page = max(0, self.ending_page - 1)
            elif click or (key and event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_RIGHT)):
                self.ending_page = (self.ending_page + 1) % 4

    def update(self, ticks):
        if self.state == "exam_intro":
            if ticks - self.exam_intro_at >= EXAM_ALERT_MS:
                self.begin_exam(ticks)
            return
        if self.state != "playing":
            return
        self.elapsed = max(0, ticks - self.phase_start)
        _, _, _, _, _, okay = DIFFICULTY[self.year]

        while (self.spawn_index < len(self.planned)
               and self.planned[self.spawn_index]["spawn"] <= self.elapsed):
            self.active.append(self.planned[self.spawn_index])
            self.spawn_index += 1

        for note in self.active[:]:
            if self.elapsed > note["arrive"] + okay:
                self.active.remove(note)
                self.miss(note, ticks)

        self.update_social(ticks)

        if self.health <= 0:
            self.state = "gameover"
            self.stop_audio()
        elif self.segment == "regular" and self.elapsed >= PHASE_MS:
            self.start_exam_intro(ticks)
        elif self.segment == "exam" and self.elapsed >= EXAM_MS:
            self.finish_semester()

    def draw_combo(self):
        """중앙 캐릭터 오른쪽의 콤보. 노트보다 먼저 그려 노트를 가리지 않음."""
        cx, cy = 622, 397
        label = SMALL_FONT.render("COMBO", True, DARK_CRIMSON)
        number = BIG_FONT.render(str(self.combo), True, CRIMSON)
        back = pygame.Surface((126, 89), pygame.SRCALPHA)
        pygame.draw.rect(back, (255, 248, 244, 192), (1, 1, 124, 87), border_radius=18)
        pygame.draw.rect(back, (175, 97, 112, 120), (1, 1, 124, 87), 2, border_radius=18)
        back.blit(label, label.get_rect(center=(63, 22)))
        back.blit(number, number.get_rect(center=(63, 57)))
        screen.blit(back, (cx - 63, cy - 44))

    def draw_hud(self):
        duration_ms = EXAM_MS if self.segment == "exam" else PHASE_MS
        remaining = max(0, (duration_ms - self.elapsed) / 1000)
        phase_label = "시험 기간" if self.segment == "exam" else f"{self.year}학년 {self.semester}학기"
        text_at(screen, FONT, phase_label, DARK_CRIMSON if self.segment == "exam" else TEXT, 24, 14)
        subtitle = "과제 · 시험 · 공부 집중!" if self.segment == "exam" else "대학 생활 생존기"
        text_at(screen, TINY_FONT, subtitle, MUTED, 24, 44)
        text_at(screen, FONT, f"남은 시간 {remaining:04.1f}초", TEXT, 385, 14)
        text_at(screen, SMALL_FONT, f"점수 {self.score:,}", TEXT, 804, 20)

        pygame.draw.rect(screen, (232, 214, 213), (24, 78, 220, 19), border_radius=9)
        w = round(216 * max(0, self.health) / START_HEALTH)
        if w > 0:
            pygame.draw.rect(screen, CRIMSON, (26, 80, w, 15), border_radius=8)
        text_at(screen, TINY_FONT, f"체력 {self.health}/{START_HEALTH}", DARK_CRIMSON, 29, 104)

        pygame.draw.rect(screen, (231, 217, 216), (380, 77, 270, 12), border_radius=6)
        progress = min(1.0, self.elapsed / duration_ms)
        if progress > 0:
            color = (209, 71, 68) if self.segment == "exam" else LIGHT_CRIMSON
            pygame.draw.rect(screen, color, (380, 77, max(1, int(270 * progress)), 12), border_radius=6)
        sound_label = ("M: 음악 " + ("켜짐" if self.sound_on else "꺼짐")
                       if self.music_name else "음악 파일 없음")
        text_at(screen, TINY_FONT, sound_label, MUTED, 768, 62)
        text_at(screen, TINY_FONT, "ESC: 종료", MUTED, 860, 659)

    def draw_shade(self, alpha=193):
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((17, 14, 25, alpha))
        screen.blit(shade, (0, 0))

    def draw_panel(self, x=95, y=65, w=810, h=575):
        self.draw_shade(179)
        pygame.draw.rect(screen, (252, 245, 240), (x, y, w, h), border_radius=24)
        pygame.draw.rect(screen, CRIMSON, (x, y, w, h), 4, border_radius=24)

    def draw_ready(self):
        self.draw_shade(175)
        center_text(screen, TITLE_FONT, "졸업할 수 있을까?", WHITE, 500, 217)
        center_text(screen, BIG_FONT, "아무 버튼이나 눌러 인생을 살아내기", (255, 217, 226), 500, 292)
        center_text(screen, SMALL_FONT,
                    f"한 학기 {SEMESTER_SECONDS}초 + 시험 기간 {EXAM_SECONDS}초 · 총 8학기",
                    WHITE, 500, 355)
        center_text(screen, SMALL_FONT, "과제·시험·공부·수업: 가운데 원에 닿을 때 클릭", WHITE, 500, 391)
        center_text(screen, SMALL_FONT, "사랑·동아리: 방 안에 잠깐 나타나면 직접 찾아서 클릭!", (255, 217, 226), 500, 423)
        pygame.draw.rect(screen, (252, 241, 238), RULES_BUTTON, border_radius=14)
        pygame.draw.rect(screen, LIGHT_CRIMSON, RULES_BUTTON, 3, border_radius=14)
        center_text(screen, FONT, "평가 기준 보기", DARK_CRIMSON, RULES_BUTTON.centerx, RULES_BUTTON.centery)
        center_text(screen, TINY_FONT,
                    "위 버튼 / H: 규칙 열기     ·     다른 키 / 화면 클릭: 시작", (225, 215, 220), 500, 556)

    def draw_rules(self):
        self.draw_panel(84, 35, 832, 625)
        center_text(screen, BIG_FONT, "게임 규칙 · 평가 기준", DARK_CRIMSON, 500, 83)
        center_text(screen, TINY_FONT,
                    "시작 전에 확인하는 판정 · 학점 · 체력 규칙", MUTED, 500, 120)
        pygame.draw.line(screen, (221, 201, 202), (115, 143), (885, 143), 2)
        for header, xx in (("판정", 151), ("점수", 344), ("감점 환산", 519), ("체력 회복", 716)):
            text_at(screen, SMALL_FONT, header, CRIMSON, xx, 153)
        judgments = (
            ("PERFECT", 300, "0", "3콤보부터 +1"),
            ("GREAT", 240, "0", "3콤보부터 +1"),
            ("GOOD", 150, "1/3개", "콤보 끊김"),
            ("OK", 60, "2/3개", "콤보 끊김"),
            ("MISS", 0, "1개", "없음"),
        )
        for idx, (name, point, penalty, heal) in enumerate(judgments):
            yy = 186 + idx * 32
            text_at(screen, SMALL_FONT, name, TEXT, 151, yy)
            text_at(screen, SMALL_FONT, str(point), TEXT, 344, yy)
            text_at(screen, SMALL_FONT, penalty, TEXT, 519, yy)
            text_at(screen, SMALL_FONT, heal, TEXT, 716, yy)
        pygame.draw.line(screen, (221, 201, 202), (115, 354), (885, 354), 2)

        text_at(screen, FONT, "학점 계산 (학업 노트)", DARK_CRIMSON, 140, 368)
        grade_lines = (
            "A+ 학업 노트 전부 PERFECT",
            "A  GOOD/OK/MISS 총 3개까지 봐줌",
            "B  유예 이후 GOOD 위주",
            "C  유예 이후 OK/MISS 또는 감점 누적",
            "D  유예 뒤 MISS 2개+ (8%↑) / 감점 16%↑",
            "F  유예 뒤 MISS 4개+ (25%↑) / 감점 35%↑",
        )
        for i, line in enumerate(grade_lines):
            text_at(screen, TINY_FONT, line, TEXT, 140, 398 + i * 17)

        text_at(screen, FONT, "체력 / 학기", DARK_CRIMSON, 574, 368)
        health_lines = (
            f"체력 최대 {START_HEALTH} · 학업 MISS -{MISS_DAMAGE_NORMAL}",
            f"수업 MISS -{MISS_DAMAGE_CLASS}",
            f"헛클릭 -{WRONG_CLICK_DAMAGE}",
            f"PERFECT/GREAT 3콤보부터 +{COMBO_HEAL_AMOUNT}",
            f"방학 체력 +{SEMESTER_RECOVERY} (최대 {START_HEALTH})",
            f"F라면 다음 학기 체력 {F_NEXT_HEALTH}",
        )
        for i, line in enumerate(health_lines):
            text_at(screen, TINY_FONT, line, TEXT, 574, 398 + i * 17)

        pygame.draw.line(screen, (221, 201, 202), (115, 508), (885, 508), 2)
        center_text(screen, TINY_FONT,
                    "사랑·동아리: 3~4초 내 클릭 · 등장 직후에는 잠깐 학업 판정 여유!", TEXT, 500, 529)
        center_text(screen, TINY_FONT,
                    "사랑·동아리는 클릭 성공/실패만 기록하며 학점·체력·콤보·점수에 영향 없음", TEXT, 500, 554)
        pygame.draw.rect(screen, CRIMSON, RULES_BACK_BUTTON, border_radius=13)
        center_text(screen, SMALL_FONT, "시작 화면으로 돌아가기", WHITE,
                    RULES_BACK_BUTTON.centerx, RULES_BACK_BUTTON.centery)

    def draw_exam_intro(self, ticks):
        self.draw_shade(213)
        center_text(screen, TITLE_FONT, "시험 기간이다!!!", WHITE, 500, 278)
        center_text(screen, FONT, "과제 · 시험 · 공부가 휘몰아친다!", (255, 210, 223), 500, 343)
        center_text(screen, TINY_FONT,
                    f"{self.year}학년 {self.semester}학기 마지막 {EXAM_SECONDS}초", WHITE, 500, 400)

    def draw_report(self):
        rec = self.records[-1]
        self.draw_panel(85, 43, 830, 615)
        center_text(screen, BIG_FONT,
                    f"{rec['year']}학년 {rec['semester']}학기 결산", DARK_CRIMSON, 500, 96)
        pygame.draw.line(screen, (221, 201, 202), (124, 132), (876, 132), 2)

        center_text(screen, SMALL_FONT, "이번 학기 학점", TEXT, 237, 158)
        center_text(screen, GRADE_FONT, rec["grade"], CRIMSON, 237, 217)
        total = rec["academic_total"]
        text_at(screen, FONT, "학업 결과", TEXT, 355, 156)
        text_at(screen, SMALL_FONT,
                f"학업 노트 {total}개 · 유예 후 감점 {rec['academic_graded_effective_misses']:.1f}개",
                MUTED, 355, 191)
        text_at(screen, TINY_FONT,
                f"실수 유예 {rec['academic_grace_used']}/{GRADE_GRACE_MISTAKES}회  ·  "
                f"실제 MISS {rec['academic_misses']}개  ·  학점 {rec['grade']}",
                MUTED, 355, 226)

        pygame.draw.line(screen, (221, 201, 202), (124, 257), (876, 257), 2)
        text_at(screen, SMALL_FONT, "학업 노트별 판정 개수", DARK_CRIMSON, 143, 266)
        columns = [("종류", 148), ("PERFECT", 246), ("GREAT", 379),
                   ("GOOD", 491), ("OK", 601), ("MISS", 704), ("합계", 808)]
        for title, xx in columns:
            text_at(screen, TINY_FONT, title, MUTED, xx, 299)
        # 학업 노트만 PERFECT/GREAT/GOOD/OK/MISS를 표시한다.
        for i, name in enumerate(ACADEMIC_NAMES):
            yy = 328 + i * 29
            counts = rec["judgments"][name]
            if i % 2 == 0:
                pygame.draw.rect(screen, (248, 236, 233), (135, yy - 4, 730, 27), border_radius=6)
            text_at(screen, SMALL_FONT, name, DARK_CRIMSON, 149, yy)
            for judgment, xx in (("PERFECT", 272), ("GREAT", 396),
                                 ("GOOD", 507), ("OK", 612), ("MISS", 720)):
                text_at(screen, SMALL_FONT, str(counts[judgment]), TEXT, xx, yy)
            text_at(screen, SMALL_FONT, str(rec["totals"][name]), TEXT, 815, yy)

        pygame.draw.line(screen, (221, 201, 202), (124, 444), (876, 444), 2)
        text_at(screen, SMALL_FONT, "인간관계 · 연애 이벤트", DARK_CRIMSON, 143, 450)
        text_at(screen, TINY_FONT, "성공", MUTED, 599, 452)
        text_at(screen, TINY_FONT, "실패", MUTED, 696, 452)
        text_at(screen, TINY_FONT, "등장", MUTED, 806, 452)
        for i, name in enumerate(SOCIAL_NAMES):
            yy = 479 + i * 28
            result = rec["social_results"][name]
            if i % 2 == 0:
                pygame.draw.rect(screen, (248, 236, 233), (135, yy - 3, 730, 26), border_radius=6)
            text_at(screen, SMALL_FONT, name, DARK_CRIMSON, 149, yy)
            text_at(screen, SMALL_FONT, str(result["success"]), TEXT, 604, yy)
            text_at(screen, SMALL_FONT, str(result["failure"]), TEXT, 702, yy)
            text_at(screen, SMALL_FONT, str(result["total"]), TEXT, 813, yy)

        pygame.draw.line(screen, (221, 201, 202), (124, 536), (876, 536), 2)
        text_at(screen, SMALL_FONT, "인간관계", CRIMSON, 143, 548)
        club_title, club_line = club_outcome(rec["hits"]["동아리"], rec["totals"]["동아리"])
        fitted_text(screen, f"{club_title} · {club_line}", TEXT, 256, 549, 605)
        text_at(screen, SMALL_FONT, "사랑", CRIMSON, 143, 578)
        love_title, love_line = romance_outcome(rec["hits"]["사랑"], rec["totals"]["사랑"])
        fitted_text(screen, f"{love_title} · {love_line}", TEXT, 256, 579, 605)
        next_message = (
            f"F 페널티! 다음 학기는 체력 {F_NEXT_HEALTH}으로 시작"
            if rec["grade"] == "F" and not (rec["year"] == 4 and rec["semester"] == 2)
            else f"방학 체력 +{SEMESTER_RECOVERY} (최대 {START_HEALTH})"
        )
        if rec["year"] == 4 and rec["semester"] == 2:
            next_message = "마지막 학기 종료! 졸업 결과를 확인하세요"
        center_text(screen, TINY_FONT,
                    "마우스 클릭 / 아무 키: 다음 학기    |    " + next_message,
                    MUTED, 500, 622)

    def draw_gameover(self):
        self.draw_shade(211)
        center_text(screen, BIG_FONT, "아앗,, 너무 지쳐버렸어,,, 휴학해버렸다!", WHITE, 500, 264)
        center_text(screen, FONT, f"{self.year}학년 {self.semester}학기에서 게임 오버", (255, 209, 220), 500, 325)
        center_text(screen, SMALL_FONT,
                    f"끝낸 학기 {len(self.records)}/8  ·  점수 {self.score:,}  ·  최고 콤보 {self.best_combo}",
                    WHITE, 500, 373)
        center_text(screen, SMALL_FONT, "아무 키나 클릭으로 새 학기 아닌 신입생부터 다시 시작", WHITE, 500, 447)

    def overall(self):
        total_academic = sum(rec["academic_total"] for rec in self.records)
        missed_academic = sum(rec["academic_effective_misses"] for rec in self.records)
        club_hits = sum(rec["hits"]["동아리"] for rec in self.records)
        club_total = sum(rec["totals"]["동아리"] for rec in self.records)
        romance_hits = sum(rec["hits"]["사랑"] for rec in self.records)
        romance_total = sum(rec["totals"]["사랑"] for rec in self.records)
        points = {"A+": 4.5, "A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}
        gpa = sum(points.get(rec["grade"], 0) for rec in self.records) / max(1, len(self.records))
        return (total_academic, missed_academic, club_hits, club_total,
                romance_hits, romance_total, gpa)

    def year_story(self, year):
        records = [rec for rec in self.records if rec["year"] == year]
        total = sum(rec["academic_total"] for rec in records)
        missed = sum(rec["academic_effective_misses"] for rec in records)
        rate = missed / total if total else 1
        club_h = sum(rec["hits"]["동아리"] for rec in records)
        club_t = sum(rec["totals"]["동아리"] for rec in records)
        romance_h = sum(rec["hits"]["사랑"] for rec in records)
        romance_t = sum(rec["totals"]["사랑"] for rec in records)

        beginnings = ["설렘 가득한 새내기로 대학에 입학했다.",
                      "익숙해진 캠퍼스에서 전공의 무게를 느꼈다.",
                      "과제와 시험이 몰아치며 진로도 고민했다.",
                      "졸업을 앞두고 마지막 학기를 버텨냈다."]
        study = (" 수업과 공부, 과제와 시험까지 충실히 해냈다." if rate < 0.10
                 else " 바쁜 와중에도 제법 성실하게 해냈다." if rate < 0.35
                 else " 성적은 아쉬워도 끝까지 버텼다." if rate < 0.65
                 else " 학점보다 생존이 우선이었다.")
        relationship = " 동기들과 많은 추억을 남겼다." if club_t and club_h / club_t >= 0.75 else " 혼자만의 시간도 많았다."
        romance = " 사랑하는 사람과 행복한 시간을 보냈다." if romance_t and romance_h / romance_t >= 0.75 else " 사랑은 생각처럼 쉽지 않았다."
        return beginnings[year - 1] + study + relationship + romance

    def draw_ending(self):
        self.draw_panel(70, 40, 860, 630)
        _, _, club_h, club_t, romance_h, romance_t, gpa = self.overall()
        if self.ending_page == 0:
            # 주요 엔딩: 8학기 성적 × 연애 × 동아리로 결정되는 이야기
            title, story = graduation_ending(
                gpa, club_h, club_t, romance_h, romance_t, self.records)
            center_text(screen, TINY_FONT, "YOUR UNIVERSITY STORY  ·  GRADUATION ENDING", MUTED, 500, 80)
            centered_fitted_text(screen, title, DARK_CRIMSON, 500, 136, 770, 36)
            pygame.draw.line(screen, (220, 198, 200), (117, 181), (883, 181), 2)

            stats = (
                ("평균 학점", f"{gpa:.2f} / 4.50"),
                ("동아리", f"{club_h}/{club_t}  ({100 * club_h / club_t:.0f}%)" if club_t else "기회 없음"),
                ("사랑", f"{romance_h}/{romance_t}  ({100 * romance_h / romance_t:.0f}%)" if romance_t else "기회 없음"),
            )
            for i, (label, value) in enumerate(stats):
                rect = pygame.Rect(124 + i * 252, 205, 244, 76)
                pygame.draw.rect(screen, (251, 240, 237), rect, border_radius=14)
                center_text(screen, TINY_FONT, label, MUTED, rect.centerx, 226)
                center_text(screen, FONT, value, DARK_CRIMSON, rect.centerx, 252)

            pygame.draw.rect(screen, (255, 251, 249), (121, 305, 758, 189), border_radius=16)
            text_at(screen, SMALL_FONT, "4년이 지나 남은 이야기", CRIMSON, 147, 321)
            wrapped_text(screen, FONT, story, TEXT, 146, 357, max_width=710, line_height=35)

            school_comment = (
                "공부만 잘한다고 좋은 대학 생활은 아니고, 좋은 학점이 쓸모없는 것도 아니다."
                if gpa >= 3.5 else
                "대학 생활의 결과는 한 장의 성적표로 다 설명할 수 없으니까."
            )
            fitted_text(screen, school_comment, MUTED, 133, 521, 745, 18)
            center_text(screen, TINY_FONT,
                        f"총점 {self.score:,}  ·  최고 콤보 {self.best_combo}  ·  끝낸 학기 {len(self.records)}/8",
                        MUTED, 500, 563)
            center_text(screen, TINY_FONT, "클릭 / 스페이스 / →: 4년간의 이야기 보기", CRIMSON, 500, 624)

        elif self.ending_page == 1:
            center_text(screen, BIG_FONT, "졸업 앨범 — 나의 4년", DARK_CRIMSON, 500, 99)
            center_text(screen, SMALL_FONT,
                        f"8학기 평균 학점 {gpa:.2f} / 4.50   ·   총점 {self.score:,}   ·   최고 콤보 {self.best_combo}",
                        TEXT, 500, 151)
            pygame.draw.line(screen, (220, 198, 200), (118, 178), (882, 178), 2)
            for i in range(1, 5):
                yy = 203 + (i - 1) * 94
                text_at(screen, SMALL_FONT, f"{i}학년", CRIMSON, 118, yy)
                story = self.year_story(i)
                wrapped_text(screen, TINY_FONT, story, TEXT,
                             201, yy, max_width=660, line_height=23)
            center_text(screen, TINY_FONT, "클릭 / 스페이스: 8학기 성적표 보기 →", MUTED, 500, 623)

        else:
            part = self.ending_page - 2
            first = part * 4
            last = first + 4
            center_text(screen, BIG_FONT,
                        "졸업 앨범 — 1·2학년" if part == 0 else "졸업 앨범 — 3·4학년",
                        DARK_CRIMSON, 500, 95)
            text_at(screen, SMALL_FONT, "학기", TEXT, 120, 145)
            text_at(screen, SMALL_FONT, "학점", TEXT, 285, 145)
            text_at(screen, SMALL_FONT, "학업 감점", TEXT, 392, 145)
            text_at(screen, SMALL_FONT, "동아리", TEXT, 580, 145)
            text_at(screen, SMALL_FONT, "사랑", TEXT, 748, 145)
            pygame.draw.line(screen, (220, 198, 200), (115, 178), (885, 178), 2)
            for i, rec in enumerate(self.records[first:last]):
                y = 192 + i * 74
                text_at(screen, SMALL_FONT, f"{rec['year']}학년 {rec['semester']}학기", TEXT, 120, y)
                text_at(screen, FONT, rec["grade"], CRIMSON, 298, y - 3)
                text_at(screen, SMALL_FONT,
                        f"{rec['academic_effective_misses']:.1f}/{rec['academic_total']}", TEXT, 405, y)
                text_at(screen, SMALL_FONT,
                        f"{rec['hits']['동아리']}/{rec['totals']['동아리']}", TEXT, 580, y)
                text_at(screen, SMALL_FONT,
                        f"{rec['hits']['사랑']}/{rec['totals']['사랑']}", TEXT, 748, y)
                pygame.draw.line(screen, (234, 221, 219), (115, y + 48), (885, y + 48), 1)

            if part == 1:
                title, line = club_outcome(club_h, club_t)
                text_at(screen, SMALL_FONT, "4년간의 인간관계", CRIMSON, 121, 510)
                fitted_text(screen, f"{title} · {line}", TEXT, 310, 513, 574)
                title, line = romance_outcome(romance_h, romance_t)
                text_at(screen, SMALL_FONT, "4년간의 연애", CRIMSON, 121, 552)
                fitted_text(screen, f"{title} · {line}", TEXT, 310, 555, 574)
            center_text(screen, TINY_FONT,
                        "클릭 / → / 스페이스: 다음 페이지   |   ←: 이전   |   R: 새 인생",
                        MUTED, 500, 625)

    def draw(self, ticks):
        draw_room(screen)
        draw_student(screen, WIDTH // 2, HEIGHT // 2 + 40, ticks)
        draw_target(screen, ticks)
        if self.state == "playing":
            self.draw_combo()  # 캐릭터 오른쪽에, 노트보다 아래 레이어로 표시
            for event in self.social_active:
                draw_social_event(screen, event, self.elapsed, ticks)
            for note in self.active:
                draw_note(screen, note, self.elapsed)
            self.draw_hud()
            if self.social_feedback and ticks - self.social_feedback["ticks"] < 800:
                msg = self.social_feedback
                center_text(screen, SMALL_FONT, msg["text"], msg["color"],
                            msg["pos"][0], msg["pos"][1] - 71)
            if ticks - self.feedback_at < 470:
                center_text(screen, FONT, self.feedback, self.feedback_color,
                            TARGET[0], TARGET[1] - 82)
        elif self.state == "exam_intro":
            self.draw_hud()
            self.draw_exam_intro(ticks)
        elif self.state == "ready":
            self.draw_ready()
        elif self.state == "rules":
            self.draw_rules()
        elif self.state == "report":
            self.draw_report()
        elif self.state == "gameover":
            self.draw_gameover()
        elif self.state == "ending":
            self.draw_ending()
        pygame.display.flip()


async def main():
    game = Game()
    while game.running:
        clock.tick(60)
        await asyncio.sleep(0)  # 브라우저 프레임 루프에 제어권 반환
        ticks = pygame.time.get_ticks()
        for event in pygame.event.get():
            game.handle_event(event, ticks)
        game.update(ticks)
        game.draw(ticks)
    game.stop_audio()
    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
