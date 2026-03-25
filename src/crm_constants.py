"""Единые константы Integram CRM — ID таблиц, реквизитов и lookup-справочники.

Единый источник истины для всего кода, работающего с CRM.
Импортировать отсюда, не из integram_api.py.
"""

# ---------------------------------------------------------------------------
# ID таблиц
# ---------------------------------------------------------------------------

TABLE_ORDERS = 1024
TABLE_CLIENTS = 1023
TABLE_PRODUCTS = 1022
TABLE_ORDER_ITEMS = 1025
TABLE_CATEGORIES = 1018
TABLE_SOURCES = 1019
TABLE_STATUSES = 1020
TABLE_DELIVERY = 1021

# Онтологические и операционные таблицы
TABLE_USERS = 4964
TABLE_STATUS_HISTORY = 6156
TABLE_HEALTH_PROFILE = 6165

# ---------------------------------------------------------------------------
# Реквизиты заказов
# ---------------------------------------------------------------------------

REQ_ORDER_DATE = "1048"
REQ_ORDER_ADDRESS = "1050"
REQ_ORDER_DELIVERY_COST = "1052"
REQ_ORDER_ITEMS_TOTAL = "1054"
REQ_ORDER_TOTAL = "1056"
REQ_ORDER_TRACKING = "1058"
REQ_ORDER_COMMENT = "1059"
REQ_ORDER_CLIENT = "1071"
REQ_ORDER_STATUS = "1073"
REQ_ORDER_DELIVERY_METHOD = "1075"
REQ_ORDER_SOURCE = "1076"
REQ_ORDER_MESSENGER = "1388"
REQ_ORDER_SHIPPED_DATE = "6360"    # Дата отправки
REQ_ORDER_DELIVERED_DATE = "6362"  # Дата доставки
REQ_ORDER_CDEK_CONFIRMED = "6416"  # Адрес СДЭК уточнён (bool)
REQ_ORDER_CLIENT_NOTIFIED = "6418" # Клиент оповещён (bool)
REQ_ORDER_STOCK_CHECKED = "6420"   # Наличие проверено (bool)

# История статусов
REQ_HISTORY_ORDER = "6157"
REQ_HISTORY_STATUS_FROM = "6158"
REQ_HISTORY_STATUS_TO = "6160"
REQ_HISTORY_DATE = "6162"
REQ_HISTORY_COMMENT = "6164"

# Профиль здоровья клиента
REQ_HEALTH_CLIENT = "6166"   # REF → Клиент
REQ_HEALTH_SYMPTOM = "6167"  # REF → Симптомы (опционально)
REQ_HEALTH_SOURCE = "6169"   # Текст факта (источник данных)
REQ_HEALTH_DATE = "6171"     # Дата записи

# ---------------------------------------------------------------------------
# Реквизиты клиентов
# ---------------------------------------------------------------------------

REQ_CLIENT_PHONE = "1036"
REQ_CLIENT_TG_ID = "1038"
REQ_CLIENT_TG_USER = "1040"
REQ_CLIENT_ADDRESS = "1042"
REQ_CLIENT_CITY = "1044"
REQ_CLIENT_COMMENT = "1046"
REQ_CLIENT_SOURCE = "1069"

# ---------------------------------------------------------------------------
# Реквизиты позиций заказа
# ---------------------------------------------------------------------------

REQ_ITEM_QTY = "1061"
REQ_ITEM_PRICE = "1063"
REQ_ITEM_SUM = "1065"
REQ_ITEM_PRODUCT = "1078"
REQ_ITEM_ORDER = "1154"

# ---------------------------------------------------------------------------
# Реквизиты товаров
# ---------------------------------------------------------------------------

REQ_PRODUCT_PRICE = "1027"
REQ_PRODUCT_WEIGHT = "1029"
REQ_PRODUCT_DESC = "1031"
REQ_PRODUCT_INSTOCK = "1033"
REQ_PRODUCT_SKU = "1035"
REQ_PRODUCT_CATEGORY = "1067"
REQ_PRODUCT_SHORT = "1173"
REQ_PRODUCT_STOCK = "4850"

# ---------------------------------------------------------------------------
# Реквизиты пользователей веб-панели
# ---------------------------------------------------------------------------

REQ_USER_PASSWORD_HASH = "4966"
REQ_USER_ROLE_OLD = "4967"
REQ_USER_ROLE = "4983"
REQ_USER_DISPLAY_NAME = "4969"
REQ_USER_ACTIVE = "4971"

# ---------------------------------------------------------------------------
# Lookup-справочники (ID записей)
# ---------------------------------------------------------------------------

# Статусы заказов
STATUS_IDS = {
    "Новый": "1086",
    "Подтверждён": "1087",
    "В сборке": "1088",
    "Отправлен": "1089",
    "Доставлен": "1090",
    "Отменён": "1091",
}

# Способы доставки
DELIVERY_IDS = {
    "СДЭК": "1092",
    "Почта России": "1093",
    "Самовывоз": "1094",
}

# Источники заказов
SOURCE_IDS = {
    "Telegram": "1082",
    "UDS": "1083",
    "WhatsApp": "1084",
    "Ручной ввод": "1085",
    "ВК": "3176",
    "Instagram": "3177",
}

# Категории товаров
CATEGORY_IDS = {
    "Продукты пчеловодства": "1079",
    "Настойки": "1080",
    "Программы здоровья": "1081",
    "Мёд": "1167",
    "Наборы": "1168",
    "Упаковка": "1169",
    "Свечи": "1170",
    "Чаи и травы": "1171",
}

# Списки для справочников
ORDER_STATUSES = list(STATUS_IDS.keys())
DELIVERY_METHODS = list(DELIVERY_IDS.keys())
