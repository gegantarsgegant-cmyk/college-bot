"""Lightweight i18n for the public site.

We don't pull in Babel/gettext — the project is small enough that a plain
nested-dict translation table is far easier to maintain. Every string the
main site shows that is *not already* coming from the database (programs,
teachers, settings) is keyed below.

Public API:
    LANGS               — supported language codes ("ru", "be", "en")
    LANG_LABELS         — display labels in their own language
    pick_language(req)  — chooses language from cookie / query / Accept-Language
    translate(key, lang) — single-key lookup with graceful fallback to RU
    register_jinja(env) — installs ``t`` global and ``trans`` filter
"""

from __future__ import annotations

from typing import Any

LANGS: tuple[str, ...] = ("ru", "be", "en")
LANG_LABELS: dict[str, str] = {"ru": "RU", "be": "BE", "en": "EN"}
LANG_FULL: dict[str, str] = {"ru": "Русский", "be": "Беларуская", "en": "English"}

# Master translation table.  Keys use dot-namespace conventions:
#   nav.*       — top navigation links
#   hero.*      — homepage hero block
#   mission.*   — "не просто учёба" section
#   programs.*  — programs section labels (cards come from DB)
#   rector.*    — слово ректора
#   teachers.*  — преподаватели section labels
#   admission.* — раздел "приём"
#   contact.*   — раздел "контакты"
#   footer.*    — site footer
#   donate.*    — /donate page labels (NOT the editable settings)
#   form.*      — application form labels & placeholders
TRANSLATIONS: dict[str, dict[str, str]] = {
    # ---------- nav ----------
    "nav.about":      {"ru": "О колледже",  "be": "Пра каледж",   "en": "About"},
    "nav.programs":   {"ru": "Программы",   "be": "Праграмы",     "en": "Programs"},
    "nav.teachers":   {"ru": "Преподаватели","be": "Выкладчыкі",  "en": "Faculty"},
    "nav.admission":  {"ru": "Приём",       "be": "Прыём",        "en": "Admission"},
    "nav.contact":    {"ru": "Контакты",    "be": "Кантакты",     "en": "Contact"},
    "nav.apply":      {"ru": "Подать заявку","be": "Падаць заяву","en": "Apply"},
    "nav.donate":     {"ru": "Поддержать",  "be": "Падтрымаць",   "en": "Support"},

    # ---------- mission ----------
    "mission.eyebrow":   {"ru": "Почему мы",            "be": "Чаму мы",         "en": "Why us"},
    "mission.headline":  {"ru": "Не просто учёба",      "be": "Не проста вучоба","en": "More than just study"},
    "mission.reasons":   {"ru": "3 причины",            "be": "3 прычыны",       "en": "3 reasons"},

    # ---------- programs ----------
    "programs.eyebrow":  {"ru": "Обучение",     "be": "Навучанне",  "en": "Education"},
    "programs.headline": {"ru": "Программы Подготовки", "be": "Праграмы падрыхтоўкі", "en": "Programs"},
    "programs.detail":   {"ru": "Подробнее",    "be": "Падрабязней","en": "Learn more"},

    # ---------- rector ----------
    "rector.eyebrow":    {"ru": "Слово ректора","be": "Слова рэктара","en": "From the Rector"},

    # ---------- teachers ----------
    "teachers.eyebrow":  {"ru": "Команда",      "be": "Каманда",    "en": "Team"},
    "teachers.headline": {"ru": "Наши преподаватели", "be": "Нашыя выкладчыкі", "en": "Our faculty"},

    # ---------- admission ----------
    "admission.eyebrow":   {"ru": "Поступление",       "be": "Паступленне",   "en": "Admission"},
    "admission.headline":  {"ru": "Приём",             "be": "Прыём",         "en": "How to apply"},
    "admission.requirements": {"ru": "Требования",     "be": "Патрабаванні",  "en": "Requirements"},
    "admission.organization": {"ru": "Организация",    "be": "Арганізацыя",   "en": "How it works"},
    "admission.dates":     {"ru": "Сроки",             "be": "Тэрміны",       "en": "Dates"},

    # ---------- contact ----------
    "contact.eyebrow":     {"ru": "Связаться",         "be": "Звязацца",      "en": "Get in touch"},
    "contact.headline":    {"ru": "Контакты",          "be": "Кантакты",      "en": "Contact"},
    "contact.address":     {"ru": "Адрес",             "be": "Адрас",         "en": "Address"},
    "contact.phone":       {"ru": "Телефон",           "be": "Тэлефон",       "en": "Phone"},
    "contact.email":       {"ru": "Эл. почта",         "be": "Эл. пошта",     "en": "Email"},
    "contact.hours":       {"ru": "Часы работы",       "be": "Гадзіны працы", "en": "Hours"},

    # ---------- footer ----------
    "footer.support":      {"ru": "Поддержать колледж","be": "Падтрымаць каледж","en": "Support the college"},
    "footer.home":         {"ru": "Главная",           "be": "Галоўная",      "en": "Home"},

    # ---------- application form ----------
    "form.title":          {"ru": "Подать заявку",     "be": "Падаць заяву",  "en": "Submit application"},
    "form.name":           {"ru": "Имя",               "be": "Імя",           "en": "First name"},
    "form.lastname":       {"ru": "Фамилия",           "be": "Прозвішча",     "en": "Last name"},
    "form.phone":          {"ru": "Телефон",           "be": "Тэлефон",       "en": "Phone"},
    "form.program":        {"ru": "Программа",         "be": "Праграма",      "en": "Program"},
    "form.church":         {"ru": "Церковь",           "be": "Царква",        "en": "Church"},
    "form.message":        {"ru": "Сообщение",         "be": "Паведамленне",  "en": "Message"},
    "form.submit":         {"ru": "Отправить",         "be": "Адправіць",     "en": "Submit"},
    "form.thanks":         {"ru": "Спасибо! Мы свяжемся с вами.","be": "Дзякуй! Мы звяжамся з вамі.","en": "Thank you! We will contact you."},

    # ---------- donate page (extra labels not in settings) ----------
    "donate.step1":           {"ru": "Шаг 1",                "be": "Крок 1",                "en": "Step 1"},
    "donate.step2":           {"ru": "Шаг 2",                "be": "Крок 2",                "en": "Step 2"},
    "donate.choose_amount":   {"ru": "Выберите сумму",       "be": "Выберыце суму",         "en": "Choose amount"},
    "donate.choose_method":   {"ru": "Выберите способ оплаты","be": "Выберыце спосаб аплаты","en": "Choose payment method"},
    "donate.method.erip":     {"ru": "ЕРИП",                 "be": "ЕРІП",                  "en": "ERIP"},
    "donate.method.card":     {"ru": "Картой онлайн",        "be": "Картай анлайн",         "en": "Card online"},
    "donate.method.bank":     {"ru": "Банк. перевод",        "be": "Банк. пераказ",         "en": "Bank transfer"},
    "donate.method.cash":     {"ru": "Наличными",            "be": "Гатоўкай",              "en": "Cash"},
    "donate.method.crypto":   {"ru": "Криптовалюта",         "be": "Крыптавалюта",          "en": "Crypto"},
    "donate.crypto.title":    {"ru": "Криптовалюта",         "be": "Крыптавалюта",          "en": "Cryptocurrency"},
    "donate.crypto.lead":     {"ru": "Принимаем пожертвования в USDT, BTC и ETH. Транзакции необратимы — проверяйте сеть перед отправкой.",
                                "be": "Прымаем ахвяраванні ў USDT, BTC і ETH. Транзакцыі незваротныя — правярайце сетку перад адпраўкай.",
                                "en": "We accept donations in USDT, BTC and ETH. Transactions are irreversible — please verify the network before sending."},
    "donate.crypto.address":  {"ru": "Адрес кошелька",       "be": "Адрас кашалька",        "en": "Wallet address"},
    "donate.crypto.network":  {"ru": "Сеть",                 "be": "Сетка",                 "en": "Network"},
    "donate.crypto.warn":     {"ru": "Убедитесь, что выбрана правильная сеть перед отправкой. Транзакции необратимы — колледж не несёт ответственности за средства, отправленные по неверным реквизитам.",
                                "be": "Пераканайцеся, што абраная правільная сетка перад адпраўкай. Транзакцыі незваротныя — каледж не нясе адказнасці за сродкі, адпраўленыя па няправільных рэквізітах.",
                                "en": "Please make sure you selected the correct network before sending. Transactions are irreversible — the college is not responsible for funds sent to wrong addresses."},
    "donate.crypto.thanks":   {"ru": "После перевода напишите нам на почту или по телефону — мы будем рады поблагодарить вас лично.",
                                "be": "Пасля пераказу напішыце нам на пошту або патэлефануйце — будзем рады падзякаваць асабіста.",
                                "en": "After sending, please email or call us — we'd love to thank you personally."},
    "donate.crypto.hint.trc20": {"ru": "Сеть: <b>TRON (TRC-20)</b>. Минимальная сумма не установлена.",
                                  "be": "Сетка: <b>TRON (TRC-20)</b>. Мінімальная сума не ўстаноўлена.",
                                  "en": "Network: <b>TRON (TRC-20)</b>. No minimum amount."},
    "donate.crypto.hint.bsc": {"ru": "Сеть: <b>BNB Smart Chain (BEP-20)</b>. Комиссия оплачивается в BNB.",
                                "be": "Сетка: <b>BNB Smart Chain (BEP-20)</b>. Камісія аплачваецца ў BNB.",
                                "en": "Network: <b>BNB Smart Chain (BEP-20)</b>. Fee is paid in BNB."},
    "donate.crypto.hint.sol": {"ru": "Сеть: <b>Solana (SPL)</b>. Комиссия оплачивается в SOL.",
                                "be": "Сетка: <b>Solana (SPL)</b>. Камісія аплачваецца ў SOL.",
                                "en": "Network: <b>Solana (SPL)</b>. Fee is paid in SOL."},
    "donate.crypto.hint.ton": {"ru": "Сеть: <b>TON</b>. Убедитесь, что ваш кошелёк поддерживает Jetton USDT.",
                                "be": "Сетка: <b>TON</b>. Пераканайцеся, што ваш кашалёк падтрымлівае Jetton USDT.",
                                "en": "Network: <b>TON</b>. Make sure your wallet supports Jetton USDT."},
    "donate.crypto.hint.btc": {"ru": "Сеть: <b>Bitcoin (BTC)</b>. Комиссия сети оплачивается отправителем.",
                                "be": "Сетка: <b>Bitcoin (BTC)</b>. Камісію сеткі аплачвае адпраўнік.",
                                "en": "Network: <b>Bitcoin (BTC)</b>. Network fee is paid by the sender."},
    "donate.crypto.hint.eth": {"ru": "Сеть: <b>Ethereum (ERC-20)</b>. Комиссия оплачивается в ETH.",
                                "be": "Сетка: <b>Ethereum (ERC-20)</b>. Камісія аплачваецца ў ETH.",
                                "en": "Network: <b>Ethereum (ERC-20)</b>. Fee is paid in ETH."},
    "donate.copy":            {"ru": "Копировать",           "be": "Скапіраваць",           "en": "Copy"},
    "donate.copied":          {"ru": "Скопировано",          "be": "Скапіравана",           "en": "Copied"},
    "donate.recipient":       {"ru": "Получатель",           "be": "Атрымальнік",           "en": "Recipient"},
    "donate.bank":            {"ru": "Банк",                 "be": "Банк",                  "en": "Bank"},
    "donate.iban":            {"ru": "IBAN",                 "be": "IBAN",                  "en": "IBAN"},
    "donate.swift":           {"ru": "SWIFT / BIC",          "be": "SWIFT / BIC",           "en": "SWIFT / BIC"},
    "donate.unp":             {"ru": "УНП",                  "be": "УНП",                   "en": "Tax ID"},
    "donate.purpose":         {"ru": "Назначение платежа",   "be": "Прызначэнне плацяжу",   "en": "Payment purpose"},
    "donate.purpose_text":    {"ru": "Добровольное пожертвование на уставную деятельность колледжа",
                                "be": "Добраахвотнае ахвяраванне на статутную дзейнасць каледжа",
                                "en": "Voluntary donation for educational activities"},
    "donate.address":         {"ru": "Адрес",                "be": "Адрас",                 "en": "Address"},
    "donate.hours":           {"ru": "Часы работы",          "be": "Гадзіны працы",         "en": "Hours"},
    "donate.phone":           {"ru": "Телефон",              "be": "Тэлефон",               "en": "Phone"},
    "donate.method_unavailable_title": {"ru": "Способ временно недоступен",
                                         "be": "Спосаб часова недаступны",
                                         "en": "Temporarily unavailable"},
    "donate.method_unavailable_body":  {"ru": "Оплата банковской картой пока подключается. Пожалуйста, воспользуйтесь вкладкой «ЕРИП» или «Банковский перевод» — они работают всегда.",
                                         "be": "Аплата банкаўскай картай пакуль падключаецца. Калі ласка, скарыстайцеся ўкладкай «ЕРІП» або «Банкаўскі пераказ» — яны працуюць заўсёды.",
                                         "en": "Card payments are being set up. Please use the ERIP or Bank transfer tab in the meantime — they always work."},
    "donate.pay_button":      {"ru": "Оплатить",             "be": "Аплаціць",              "en": "Pay"},
    "donate.cancel":          {"ru": "Отменить",             "be": "Скасаваць",             "en": "Cancel"},
    "donate.back_to_site":    {"ru": "← На сайт",            "be": "← На сайт",             "en": "← Back to site"},
    "donate.why_title.1":     {"ru": "Стипендии студентам",  "be": "Стыпендыі студэнтам",   "en": "Student scholarships"},
    "donate.why_text.1":      {"ru": "Помогаем учиться студентам из малообеспеченных семей и иногородним.",
                                "be": "Дапамагаем вучыцца студэнтам з малазабяспечаных сем'яў і іншагароднім.",
                                "en": "Helping students from low-income families and out-of-town students."},
    "donate.why_title.2":     {"ru": "Учебная литература",   "be": "Навучальная літаратура","en": "Educational materials"},
    "donate.why_text.2":      {"ru": "Богословские книги, ноты, учебники — всё, что нужно для подготовки служителей.",
                                "be": "Багаслоўскія кнігі, ноты, падручнікі — усё, што патрэбна для падрыхтоўкі служыцеляў.",
                                "en": "Theology books, sheet music, textbooks — everything needed to prepare ministers."},
    "donate.why_title.3":     {"ru": "Здание и служения",    "be": "Будынак і служэнні",    "en": "Building and ministry"},
    "donate.why_text.3":      {"ru": "Содержание учебного корпуса, музыкальных инструментов и оборудования для занятий.",
                                "be": "Утрыманне навучальнага корпуса, музычных інструментаў і абсталявання для заняткаў.",
                                "en": "Maintaining the building, musical instruments and classroom equipment."},

    # ---------- 404 / errors ----------
    "error.404": {"ru": "Страница не найдена", "be": "Старонка не знойдзена", "en": "Page not found"},
}


def translate(key: str, lang: str = "ru") -> str:
    """Return the translation for ``key`` in ``lang`` (falls back to RU then key)."""
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    return entry.get(lang) or entry.get("ru") or key


def pick_language(request: Any) -> str:
    """Pick the active language for ``request``.

    Resolution order:
      1. ``?lang=`` query parameter (used by the language switcher)
      2. ``lang`` cookie set by the switcher
      3. ``Accept-Language`` header
      4. Default to RU.
    """
    # 1. ?lang=
    qp = request.query_params.get("lang") if hasattr(request, "query_params") else None
    if qp and qp in LANGS:
        return qp

    # 2. cookie
    cookie = request.cookies.get("lang") if hasattr(request, "cookies") else None
    if cookie and cookie in LANGS:
        return cookie

    # 3. Accept-Language
    al = request.headers.get("accept-language", "") if hasattr(request, "headers") else ""
    for chunk in al.split(","):
        code = chunk.strip().split(";")[0].lower()
        # Belarusian — "be", "be-by"
        if code.startswith("be"):
            return "be"
        if code.startswith("en"):
            return "en"
        if code.startswith("ru"):
            return "ru"

    return "ru"


def register_jinja(env: Any) -> None:
    """Install ``t(key, lang)`` global and ``trans`` filter on a Jinja env."""
    def _t(key: str, lang: str = "ru") -> str:
        return translate(key, lang)

    env.globals["t"] = _t
    env.filters["trans"] = _t
    env.globals["LANGS"] = LANGS
    env.globals["LANG_LABELS"] = LANG_LABELS
    env.globals["LANG_FULL"] = LANG_FULL
