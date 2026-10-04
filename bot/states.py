"""FSM-состояния бота."""
from aiogram.fsm.state import State, StatesGroup


class UserSG(StatesGroup):
    promo_code = State()


class AccSG(StatesGroup):
    login = State()
    password = State()
    games = State()


class BulkSG(StatesGroup):
    file = State()


class EditSG(StatesGroup):
    value = State()


class ChSG(StatesGroup):
    chat = State()
    link = State()


class PromoSG(StatesGroup):
    code = State()
    amount = State()
    max_uses = State()
    days = State()


class UsersSG(StatesGroup):
    tid = State()


class AdSG(StatesGroup):
    text = State()
    button = State()
    url = State()


class DonSetSG(StatesGroup):
    amount = State()
