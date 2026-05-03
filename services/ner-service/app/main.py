import os
import re
from abc import ABC, abstractmethod
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title='ner-service')
INTERNAL = os.getenv('INTERNAL_SERVICE_TOKEN', 'internal-secret-token')


class Entity(BaseModel):
    type: str
    text: str
    start: int
    end: int
    confidence: float
    source: str


class ExtractRequest(BaseModel):
    text: str
    language: str = 'ru'


class BaseNerProvider(ABC):
    @abstractmethod
    def extract(self, text: str) -> list[Entity]:
        raise NotImplementedError


class RegexRuleNerProvider(BaseNerProvider):
    def __init__(self) -> None:
        self.patterns = [
            ('EMAIL', re.compile(r'[\w\.-]+@[\w\.-]+'), 0.95),
            ('PHONE', re.compile(r'(?:\+7|8)[\s\-()]?\d{3}[\s\-()]?\d{3}[\s\-()]?\d{2}[\s\-()]?\d{2}'), 0.93),
            ('SNILS', re.compile(r'\d{3}-\d{3}-\d{3}\s\d{2}'), 0.92),
            ('INN', re.compile(r'\b\d{10}(?:\d{2})?\b'), 0.88),
            ('PASSPORT', re.compile(r'\b\d{4}\s?\d{6}\b'), 0.88),
            ('BIRTH_DATE', re.compile(r'\b\d{2}\.\d{2}\.\d{4}\b'), 0.86),
            ('PERSON_FULL_NAME', re.compile(r'[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+'), 0.85),
            ('ADDRESS', re.compile(r'(?:г\.|город)\s?[А-ЯЁа-яё\-]+,?\s?(?:ул\.|улица)\s?[А-ЯЁа-яё\-]+,?\s?(?:д\.|дом)\s?\d+'), 0.8),
        ]
        self.role_based = re.compile(r'(истец|ответчик|с участием|председательствующего судьи|при секретаре)\s+([А-ЯЁ][а-яё]+\s?[А-ЯЁ]\.[А-ЯЁ]\.)', re.IGNORECASE)

    def extract(self, text: str) -> list[Entity]:
        entities: list[Entity] = []
        for etype, pattern, conf in self.patterns:
            for m in pattern.finditer(text):
                entities.append(Entity(type=etype, text=m.group(0), start=m.start(), end=m.end(), confidence=conf, source='regex'))
        for m in self.role_based.finditer(text):
            entities.append(Entity(type='CASE_PARTICIPANT', text=m.group(2), start=m.start(2), end=m.end(2), confidence=0.82, source='rule'))
        entities.sort(key=lambda x: (x.start, -(x.end - x.start)))
        return entities


provider: BaseNerProvider = RegexRuleNerProvider()


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/ready')
def ready():
    return {'status': 'ready'}


@app.post('/internal/ner/extract')
def extract(body: ExtractRequest, x_internal_service_token: str | None = Header(None)):
    if x_internal_service_token != INTERNAL:
        raise HTTPException(403, detail={'error': {'code': 'ACCESS_DENIED', 'message': 'Недостаточно прав', 'details': {}}})
    return {'entities': [entity.model_dump() for entity in provider.extract(body.text)]}
