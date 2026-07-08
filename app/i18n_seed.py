"""Seed dictionaries used to back-fill BE/EN overrides for the existing
catalogue of teacher names, roles, and subjects on first run.

Anything not in these dicts is left alone — admin can still edit each
row's i18n payload through `/admin/teachers`.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Cyrillic → Latin transliteration (Russian / Belarusian → English)
# ---------------------------------------------------------------------------

_RU_LATIN: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ў": "u",
}


def _latin(s: str) -> str:
    out: list[str] = []
    for ch in s:
        lower = ch.lower()
        rep = _RU_LATIN.get(lower, ch)
        if ch.isupper() and rep:
            rep = rep[0].upper() + rep[1:]
        out.append(rep)
    return "".join(out)


def transliterate_name_en(name: str) -> str:
    """First name + middle initial + last name (Western order).

    'Пётр Викентьевич Ашейчик' → 'Petr V. Asheychik'
    """
    if not name:
        return ""
    parts = name.split()
    if len(parts) >= 3:
        first, middle, *rest = parts
        last = rest[-1]
        return f"{_latin(first)} {_latin(middle)[0]}. {_latin(last)}"
    if len(parts) == 2:
        return f"{_latin(parts[0])} {_latin(parts[1])}"
    return _latin(name)


# ---------------------------------------------------------------------------
# Russian → Belarusian transliteration of personal names
# Belarusian uses different letters: и→і, щ→шч, ъ stays absent, ё mostly stays.
# ---------------------------------------------------------------------------

_RU_BE: dict[str, str] = {
    "и": "і", "щ": "шч", "ъ": "",
}


def transliterate_name_be(name: str) -> str:
    """Naive RU→BE transliteration that handles the most visible letter swaps."""
    if not name:
        return ""
    out: list[str] = []
    for ch in name:
        lower = ch.lower()
        rep = _RU_BE.get(lower, ch)
        if ch.isupper() and rep:
            rep = rep[0].upper() + rep[1:]
        out.append(rep)
    return "".join(out)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

ROLE_EN: dict[str, str] = {
    "Преподаватель": "Faculty member",
    "Преподаватель · Бакалавр богословия": "Faculty member · Bachelor of Theology",
    "Преподаватель · Бакалавр искусств": "Faculty member · Bachelor of Arts",
    "Преподаватель · Режиссёр театра": "Faculty member · Theatre director",
    "Ректор · Доктор богословия": "Rector · Doctor of Theology",
    "Проректор · Магистр богословия": "Vice-Rector · Master of Theology",
    "Проректор по учебной работе · Магистр богословия": "Vice-Rector for Academics · Master of Theology",
    "Зав. богословским отделением · Магистр богословия": "Head of Theology Department · Master of Theology",
    "Зав. богосл. отделением · Магистр": "Head of Theology Dept. · Master",
    "Академический куратор · Магистр богословия": "Academic supervisor · Master of Theology",
    "Доктор богословия · Епископ ОЦ ХВЕ": "Doctor of Theology · Bishop of UC CFEF",
    "Доктор практического богословия · Пастор": "Doctor of Practical Theology · Pastor",
    "Бакалавр богословия · Пастор": "Bachelor of Theology · Pastor",
}

ROLE_BE: dict[str, str] = {
    "Преподаватель": "Выкладчык",
    "Преподаватель · Бакалавр богословия": "Выкладчык · Бакалаўр тэалогіі",
    "Преподаватель · Бакалавр искусств": "Выкладчык · Бакалаўр мастацтваў",
    "Преподаватель · Режиссёр театра": "Выкладчык · Рэжысёр тэатра",
    "Ректор · Доктор богословия": "Рэктар · Доктар тэалогіі",
    "Проректор · Магистр богословия": "Прарэктар · Магістр тэалогіі",
    "Проректор по учебной работе · Магистр богословия": "Прарэктар па навучальнай рабоце · Магістр тэалогіі",
    "Зав. богословским отделением · Магистр богословия": "Загадчык тэалагічнага аддзялення · Магістр тэалогіі",
    "Зав. богосл. отделением · Магистр": "Загадчык тэал. аддзялення · Магістр",
    "Академический куратор · Магистр богословия": "Акадэмічны куратар · Магістр тэалогіі",
    "Доктор богословия · Епископ ОЦ ХВЕ": "Доктар тэалогіі · Епіскап АЦ ХВЕ",
    "Доктор практического богословия · Пастор": "Доктар практычнай тэалогіі · Пастар",
    "Бакалавр богословия · Пастор": "Бакалаўр тэалогіі · Пастар",
}

# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------

SUBJECT_EN: dict[str, str] = {
    "Актёрское мастерство": "Acting",
    "Анализ музыкальных произведений": "Music analysis",
    "Апологетика": "Apologetics",
    "Бас-гитара": "Bass guitar",
    "Библейское лидерство": "Biblical leadership",
    "Брак и семья": "Marriage and family",
    "Введение в Библию": "Introduction to the Bible",
    "Введение в евангельское вероучение": "Introduction to evangelical doctrine",
    "Введение в систематическое богословие": "Introduction to systematic theology",
    "Вокал": "Vocals",
    "Гармония": "Harmony",
    "Герменевтика": "Hermeneutics",
    "Гитара": "Guitar",
    "Дары служений": "Spiritual gifts",
    "Деяния Святых Апостолов": "Acts of the Apostles",
    "Деяния апостолов": "Acts of the Apostles",
    "Душепопечение": "Pastoral counselling",
    "Жизнь Иисуса Христа": "Life of Jesus Christ",
    "Звукорежиссура": "Sound engineering",
    "Исторические книги Библии": "Historical books of the Bible",
    "История музыки": "Music history",
    "История церкви": "Church history",
    "Клавишные инструменты": "Keyboard instruments",
    "Композиция": "Composition",
    "Малые пророки": "Minor prophets",
    "Методы изучения Библии": "Bible study methods",
    "Музыкальная литература": "Music literature",
    "Обзор Ветхого Завета": "Old Testament survey",
    "Обзор Нового Завета": "New Testament survey",
    "Обзор НЗ": "NT survey",
    "Обзор ВЗ": "OT survey",
    "Общее фортепиано": "General piano",
    "Основы компьютерной аранжировки": "Computer arranging basics",
    "Основы права": "Foundations of law",
    "Пасторское богословие": "Pastoral theology",
    "Пластика": "Stage movement",
    "Полифония": "Polyphony",
    "Послания к Коринфянам": "Letters to the Corinthians",
    "Послания к Римлянам и Галатам": "Letters to the Romans and Galatians",
    "Правила написания академических работ": "Academic writing",
    "Практическая герменевтика": "Practical hermeneutics",
    "Практическое христианство": "Practical Christianity",
    "Призвание": "Calling",
    "Пророческая литература": "Prophetic literature",
    "Пятикнижие": "Pentateuch",
    "Работа в нотном редакторе": "Music notation software",
    "Ритмическое сольфеджио": "Rhythmic solfège",
    "Синоптические Евангелия": "Synoptic Gospels",
    "Синоптические евангелия": "Synoptic Gospels",
    "Систематическое богословие": "Systematic theology",
    "Современные герменевтические подходы": "Contemporary hermeneutical approaches",
    "Сольфеджио": "Solfège",
    "Сравнительное богословие": "Comparative theology",
    "Сценическая речь. Культура речи": "Stage speech. Speech culture",
    "Теория музыки": "Music theory",
    "Ударные": "Drums",
    "Философия": "Philosophy",
    "Фортепиано": "Piano",
    "Хвала и поклонение": "Worship",
    "Хоровое сольфеджио": "Choral solfège",
    "Хоровое пение": "Choir",
    "Христ. этика": "Christian ethics",
    "Христианская жизнь": "Christian life",
    "Христианская педагогика": "Christian pedagogy",
    "Христианская этика": "Christian ethics",
    "Церковь в плюралистическом обществе": "Church in a pluralistic society",
    "Экзегетика": "Exegesis",
    "Электрогитара": "Electric guitar",
}

SUBJECT_BE: dict[str, str] = {
    "Актёрское мастерство": "Акцёрскае майстэрства",
    "Анализ музыкальных произведений": "Аналіз музычных твораў",
    "Апологетика": "Апалагетыка",
    "Бас-гитара": "Бас-гітара",
    "Библейское лидерство": "Біблейскае лідарства",
    "Брак и семья": "Шлюб і сям'я",
    "Введение в Библию": "Уводзіны ў Біблію",
    "Введение в евангельское вероучение": "Уводзіны ў евангельскае веравучэнне",
    "Введение в систематическое богословие": "Уводзіны ў сістэматычную тэалогію",
    "Вокал": "Вакал",
    "Гармония": "Гармонія",
    "Герменевтика": "Герменеўтыка",
    "Гитара": "Гітара",
    "Дары служений": "Дары служэнняў",
    "Деяния Святых Апостолов": "Дзеі святых апосталаў",
    "Деяния апостолов": "Дзеі апосталаў",
    "Душепопечение": "Душэпапячэнне",
    "Жизнь Иисуса Христа": "Жыццё Ісуса Хрыста",
    "Звукорежиссура": "Гукарэжысура",
    "Исторические книги Библии": "Гістарычныя кнігі Бібліі",
    "История музыки": "Гісторыя музыкі",
    "История церкви": "Гісторыя царквы",
    "Клавишные инструменты": "Клавішныя інструменты",
    "Композиция": "Кампазіцыя",
    "Малые пророки": "Малыя прарокі",
    "Методы изучения Библии": "Метады вывучэння Бібліі",
    "Музыкальная литература": "Музычная літаратура",
    "Обзор Ветхого Завета": "Агляд Старога Запавету",
    "Обзор Нового Завета": "Агляд Новага Запавету",
    "Обзор НЗ": "Агляд НЗ",
    "Обзор ВЗ": "Агляд СЗ",
    "Общее фортепиано": "Агульнае фартэпіяна",
    "Основы компьютерной аранжировки": "Асновы кампутарнай аранжыроўкі",
    "Основы права": "Асновы права",
    "Пасторское богословие": "Пастарская тэалогія",
    "Пластика": "Пластыка",
    "Полифония": "Поліфанія",
    "Послания к Коринфянам": "Пасланні да Карынфянаў",
    "Послания к Римлянам и Галатам": "Пасланні да Рымлянаў і Галатаў",
    "Правила написания академических работ": "Правілы напісання акадэмічных прац",
    "Практическая герменевтика": "Практычная герменеўтыка",
    "Практическое христианство": "Практычнае хрысціянства",
    "Призвание": "Пакліканне",
    "Пророческая литература": "Прарочая літаратура",
    "Пятикнижие": "Пяцікніжжа",
    "Работа в нотном редакторе": "Праца ў нотным рэдактары",
    "Ритмическое сольфеджио": "Рытмічнае сальфеджыа",
    "Синоптические Евангелия": "Сінаптычныя Евангеллі",
    "Синоптические евангелия": "Сінаптычныя евангеллі",
    "Систематическое богословие": "Сістэматычная тэалогія",
    "Современные герменевтические подходы": "Сучасныя герменеўтычныя падыходы",
    "Сольфеджио": "Сальфеджыа",
    "Сравнительное богословие": "Параўнальная тэалогія",
    "Сценическая речь. Культура речи": "Сцэнічная мова. Культура мовы",
    "Теория музыки": "Тэорыя музыкі",
    "Ударные": "Ударныя",
    "Философия": "Філасофія",
    "Фортепиано": "Фартэпіяна",
    "Хвала и поклонение": "Хвала і пакланенне",
    "Хоровое сольфеджио": "Харавое сальфеджыа",
    "Хоровое пение": "Харавы спеў",
    "Христ. этика": "Хрысціянская этыка",
    "Христианская жизнь": "Хрысціянскае жыццё",
    "Христианская педагогика": "Хрысціянская педагогіка",
    "Христианская этика": "Хрысціянская этыка",
    "Церковь в плюралистическом обществе": "Царква ў плюралістычным грамадстве",
    "Экзегетика": "Экзегетыка",
    "Электрогитара": "Электрагітара",
}


def translate_role(role: str, lang: str) -> str:
    table = ROLE_EN if lang == "en" else ROLE_BE if lang == "be" else {}
    if not role:
        return ""
    return table.get(role.strip(), role)


def translate_subjects(subjects: list[str], lang: str) -> list[str]:
    table = SUBJECT_EN if lang == "en" else SUBJECT_BE if lang == "be" else {}
    return [table.get((s or "").strip(), s) for s in (subjects or [])]


def translate_name(name: str, lang: str) -> str:
    if lang == "en":
        return transliterate_name_en(name)
    if lang == "be":
        return transliterate_name_be(name)
    return name


# ---------------------------------------------------------------------------
# Programs (homepage cards) — seed by program slug.
# Each lang has a {field: value} dict; only fields present here are filled.
# ---------------------------------------------------------------------------

PROGRAM_SEEDS: dict[str, dict[str, dict[str, str]]] = {
    "music": {
        "en": {
            "tag": "Music ministry",
            "title": "Bachelor of Church Music",
            "description": "Training musicians for ministry",
            "form_label": "Part-time",
            "term_label": "2 levels",
            "degree_label": "Bachelor of Arts",
        },
        "be": {
            "tag": "Музычнае служэнне",
            "title": "Бакалаўр царкоўнай музыкі",
            "description": "Падрыхтоўка музыкаў для служэння",
            "form_label": "Завочна-вочная",
            "term_label": "2 узроўні",
            "degree_label": "Бакалаўр мастацтваў",
        },
    },
    "theology": {
        "en": {
            "tag": "Biblical & theological",
            "title": "Theology and Christian Ministry",
            "description": (
                "Studying Scripture across three levels — from a basic "
                "certificate up to a Bachelor of Theology. Fully online."
            ),
            "form_label": "Distance (online)",
            "term_label": "From 1 year (Level A) up to 4 years (Level C)",
            "degree_label": "Bachelor of Ministry / Theology",
        },
        "be": {
            "tag": "Біблейска-багаслоўскае",
            "title": "Тэалогія і хрысціянскае служэнне",
            "description": (
                "Вывучэнне Святога Пісання на трох узроўнях — ад базавага "
                "сертыфіката да ступені бакалаўра тэалогіі. Цалкам онлайн."
            ),
            "form_label": "Завочная (онлайн)",
            "term_label": "Ад 1 года (Узровень А) да 4 гадоў (Узровень C)",
            "degree_label": "Бакалаўр служэння / тэалогіі",
        },
    },
    "theatre": {
        "en": {
            "tag": "Gospel through art",
            "title": "Bachelor of Arts in Theatre Ministry",
            "description": (
                "Practical skills of church theatre ministry. A combination "
                "of theological and specialised training for ministry through art."
            ),
            "form_label": "Part-time · 4 sessions/year",
            "term_label": "3 years",
            "degree_label": "Bachelor of Arts",
        },
        "be": {
            "tag": "Евангелле праз творчасць",
            "title": "Бакалаўр мастацтваў у тэатральным служэнні",
            "description": (
                "Практычныя навыкі царкоўнага тэатральнага служэння. "
                "Спалучэнне багаслоўскай і спецыяльнай падрыхтоўкі для "
                "служэння творчасцю."
            ),
            "form_label": "Завочна-вочная · 4 сесіі/год",
            "term_label": "3 гады",
            "degree_label": "Бакалаўр мастацтваў",
        },
    },
}


def program_seed(slug: str, lang: str) -> dict[str, str]:
    return PROGRAM_SEEDS.get(slug, {}).get(lang, {})
