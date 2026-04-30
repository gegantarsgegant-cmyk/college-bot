from aiogram.fsm.state import State, StatesGroup


class NewsCreate(StatesGroup):
    title = State()
    body = State()
    photo = State()


class EventCreate(StatesGroup):
    title = State()
    starts_at = State()
    location = State()


class TeacherCreate(StatesGroup):
    name = State()
    role = State()
    bio = State()
    subjects = State()
    departments = State()


class DocumentCreate(StatesGroup):
    title = State()
    file = State()


class GalleryCreate(StatesGroup):
    photo = State()


class ApplyFlow(StatesGroup):
    name = State()
    lastname = State()
    phone = State()
    program = State()
    church = State()
