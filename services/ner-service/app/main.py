import logging
import os
import re
from abc import ABC, abstractmethod
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title='ner-service')
INTERNAL = os.getenv('INTERNAL_SERVICE_TOKEN', 'internal-secret-token')
LOGGER = logging.getLogger(__name__)


class Entity(BaseModel):
    type: str
    text: str
    normalized_text: str | None = None
    start: int
    end: int
    confidence: float
    source: str


class ExtractRequest(BaseModel):
    text: str
    language: str = 'ru'


class BaseNerProvider(ABC):
    name = 'base'

    @abstractmethod
    def extract(self, text: str) -> list[Entity]:
        raise NotImplementedError


def map_natasha_type(span_type: str) -> str:
    return {
        'PER': 'PERSON_FULL_NAME',
        'LOC': 'LOCATION',
        'ORG': 'ORGANIZATION',
    }.get(span_type, span_type)




class RussianPersonNormalizer:
    def __init__(self, morph_vocab=None):
        self.morph_vocab = morph_vocab
        self.names_extractor = None
        if morph_vocab is not None:
            try:
                from natasha import NamesExtractor
                self.names_extractor = NamesExtractor(morph_vocab)
            except Exception:
                self.names_extractor = None
        self.initials_patterns = [
            re.compile(r'^([А-ЯЁ][а-яё]+)\s+([А-ЯЁ])\.\s*([А-ЯЁ])\.$'),
            re.compile(r'^([А-ЯЁ])\.\s*([А-ЯЁ])\.\s*([А-ЯЁ][а-яё]+)$'),
        ]

    def normalize(self, text: str) -> tuple[str | None, dict]:
        value = re.sub(r'\s+', ' ', text or '').strip().replace(' .', '.')
        meta = {'format': 'FULL', 'word_order': 'SURNAME_NAME_PATRONYMIC', 'initials': None, 'surname_normalized': None}
        for p in self.initials_patterns:
            m = p.match(value)
            if m:
                if p.pattern.startswith('^([А-ЯЁ][а-яё]+)'):
                    surname, i1, i2 = m.groups(); order='SURNAME_INITIALS'
                else:
                    i1, i2, surname = m.groups(); order='INITIALS_SURNAME'
                sn = self._normalize_word(surname)
                meta.update({'format':'INITIALS','word_order':order,'initials':f'{i1}{i2}','surname_normalized':sn})
                return f'{sn} {i1}.{i2}.', meta
        parts = value.split()
        if len(parts) >= 3:
            s, n, p = parts[:3]
            sn, nn, pn = self._normalize_full_name_parts(value, s, n, p)
            meta.update({'surname_normalized': sn, 'initials': f'{nn[0]}{pn[0]}', 'word_order': 'SURNAME_NAME_PATRONYMIC'})
            return f'{sn} {nn} {pn}', meta
        return None, meta

    def _normalize_full_name_parts(self, text: str, s: str, n: str, p: str) -> tuple[str, str, str]:
        if self.names_extractor is not None:
            try:
                matches = list(self.names_extractor(text))
                if matches:
                    fact = matches[0].fact
                    sn = (fact.last or s)
                    nn = (fact.first or n)
                    pn = (fact.middle or p)
                    return self._normalize_word(sn), self._normalize_word(nn), self._normalize_word(pn)
            except Exception:
                pass
        return self._normalize_word(s), self._normalize_word(n), self._normalize_word(p)

    def _normalize_word(self, word: str) -> str:
        if not word:
            return word
        try:
            from natasha import Doc
            d = Doc(word)
            d.segment(lambda x: None)
        except Exception:
            pass
        try:
            from pymorphy3 import MorphAnalyzer
            m = MorphAnalyzer()
            p = m.parse(word)[0]
            return p.normal_form.capitalize()
        except Exception:
            lw = word.lower()
            # lightweight russian name fallback for common declensions
            for src, dst in [
                ('ым', ''), ('им', ''), ('ом', ''), ('ем', ''),
                ('ого', 'ий'), ('его', 'ий'),
                ('ову', 'ов'), ('еву', 'ев'), ('ину', 'ин'),
                ('ова', 'ов'), ('ева', 'ев'), ('ина', 'ин'),
                ('ича', 'ич'), ('овича', 'ович'), ('евича', 'евич'),
                ('ьевича', 'ьевич'), ('овне', 'овна'), ('евне', 'евна'),
                ('ича', 'ич'), ('ия', 'ий'), ('ея', 'ей'),
                ('у', ''), ('ю', ''), ('а', ''), ('я', ''),
            ]:
                if lw.endswith(src) and len(lw) > len(src) + 2:
                    return (lw[:-len(src)] + dst).capitalize()
            return word.capitalize()


class NatashaNerProvider(BaseNerProvider):
    name = 'natasha'

    def __init__(self):
        from natasha import (
            Segmenter,
            MorphVocab,
            NewsEmbedding,
            NewsMorphTagger,
            NewsSyntaxParser,
            NewsNERTagger,
            Doc,
        )

        self.doc_cls = Doc
        self.segmenter = Segmenter()
        self.morph_vocab = MorphVocab()
        self.emb = NewsEmbedding()
        self.morph_tagger = NewsMorphTagger(self.emb)
        self.syntax_parser = NewsSyntaxParser(self.emb)
        self.ner_tagger = NewsNERTagger(self.emb)
        self.person_normalizer = RussianPersonNormalizer(self.morph_vocab)

    def extract(self, text: str) -> list[Entity]:
        doc = self.doc_cls(text)
        doc.segment(self.segmenter)
        doc.tag_morph(self.morph_tagger)
        doc.parse_syntax(self.syntax_parser)
        doc.tag_ner(self.ner_tagger)

        entities: list[Entity] = []
        for span in doc.spans:
            span.normalize(self.morph_vocab)
            mapped_type = map_natasha_type(span.type)
            if mapped_type in {'PERSON_FULL_NAME', 'LOCATION', 'ORGANIZATION'}:
                normalized_text = getattr(span, 'normal', None) or span.text
                if mapped_type == 'PERSON_FULL_NAME':
                    normalized_text = self.person_normalizer.normalize(normalized_text)[0] or normalized_text
                if not getattr(span, 'normal', None):
                    LOGGER.info('Natasha normalization missing for span: %s', span.text)
                entities.append(Entity(
                    type=mapped_type,
                    text=span.text,
                    normalized_text=normalized_text,
                    start=span.start,
                    end=span.stop,
                    confidence=0.90,
                    source='natasha',
                ))
        return entities


class RegexRuleNerProvider(BaseNerProvider):
    name = 'regex'

    def __init__(self) -> None:
        flags = re.IGNORECASE | re.UNICODE
        fio_full = r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+'
        fio_initials = r'[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.'
        fio = rf'(?:{fio_full}|{fio_initials})'
        try:
            from natasha import MorphVocab
            self.person_normalizer = RussianPersonNormalizer(MorphVocab())
        except Exception:
            self.person_normalizer = RussianPersonNormalizer()
        self.patterns = [
            ('EMAIL', re.compile(r'(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-яЁё]{2,}\b'), 0.95, 'regex'),
            ('PHONE', re.compile(r'(?<!\d)(?:\+7|8)[\s\-()]?\d{3}[\s\-()]?\d{3}[\s\-()]?\d{2}[\s\-()]?\d{2}(?!\d)'), 0.93, 'regex'),
            ('SNILS', re.compile(r'\b\d{3}-\d{3}-\d{3}\s?\d{2}\b'), 0.92, 'regex'),
            ('INN', re.compile(r'\b\d{10}(?:\d{2})?\b'), 0.88, 'regex'),
            ('PASSPORT', re.compile(r'\bпаспорт(?:\s+серии)?\s*\d{2}\s?\d{2}(?:\s+номер)?\s*\d{6}\b|\b\d{4}\s?\d{6}\b', flags), 0.88, 'regex'),
            ('DATE', re.compile(r'\b\d{2}\.\d{2}\.\d{4}\b', flags), 0.86, 'regex'),
            ('PERSON_FULL_NAME', re.compile(fio), 0.85, 'regex'),
            ('ORGANIZATION', re.compile(r'\b(?:ООО|АО|ПАО|ЗАО|ОАО)\s+[«"][^»"]+[»"]', flags), 0.82, 'rule'),
            ('ADDRESS', re.compile(r'\b(?:(?:г\.|город)\s*[А-ЯЁа-яё\- ]+|(?:ул\.|улица)\s*[А-ЯЁа-яё\- ]+|(?:д\.|дом)\s*\d+[А-Яа-я]?)(?:,?\s*(?:(?:ул\.|улица)\s*[А-ЯЁа-яё\- ]+|(?:д\.|дом)\s*\d+[А-Яа-я]?))*', flags), 0.80, 'regex'),
            ('LOCATION', re.compile(r'\b(?:г\.|город)\s*[А-ЯЁа-яё\- ]+', flags), 0.78, 'regex'),
        ]
        role_specs = [
            ('JUDGE', r'(?:судья|председательствующего\s+судьи|под\s+председательством)'),
            ('COURT_SECRETARY', r'(?:при\s+секретаре)'),
            ('CASE_PARTICIPANT', r'(?:истец|ответчик|заявитель|подсудимый|лицо,\s*привлекаемое\s+к\s+административной\s+ответственности|с\s+участием|в\s+отношении)'),
        ]
        self.role_patterns = [
            (etype, re.compile(rf'\b{prefix}\s+(?:[^.\n,;:]*?\s+)?({fio})', flags), 0.87 if etype != 'CASE_PARTICIPANT' else 0.82)
            for etype, prefix in role_specs
        ]

    def extract(self, text: str) -> list[Entity]:
        entities: list[Entity] = []
        for etype, pattern, conf, source in self.patterns:
            for m in pattern.finditer(text):
                value = m.group(0).strip(' ,;')
                start = m.start() + (len(m.group(0)) - len(m.group(0).lstrip(' ,;')))
                normalized = None
                if etype in {'PERSON_FULL_NAME','JUDGE','COURT_SECRETARY','CASE_PARTICIPANT'}:
                    normalized = self.person_normalizer.normalize(value)[0] or value
                entities.append(Entity(type=etype, text=value, normalized_text=normalized, start=start, end=start + len(value), confidence=conf, source=source))
        for etype, pattern, conf in self.role_patterns:
            for m in pattern.finditer(text):
                person_text = m.group(1)
                normalized = self.person_normalizer.normalize(person_text)[0] or person_text
                entities.append(Entity(type=etype, text=person_text, normalized_text=normalized, start=m.start(1), end=m.end(1), confidence=conf, source='rule'))
        return deduplicate_entities(entities)


FORMAL_TYPES = {'EMAIL', 'PHONE', 'SNILS', 'INN', 'PASSPORT'}
NATASHA_TYPES = {'PERSON_FULL_NAME', 'LOCATION', 'ORGANIZATION'}


def entity_priority(entity: Entity) -> int:
    if entity.type in FORMAL_TYPES and entity.source in {'regex', 'rule'}:
        return 4
    if entity.type in NATASHA_TYPES and entity.source == 'natasha':
        return 3
    if entity.source == 'rule':
        return 2
    return 1


def overlaps(left: Entity, right: Entity) -> bool:
    return left.start < right.end and right.start < left.end


def choose_entity(current: Entity, candidate: Entity) -> Entity:
    current_key = (entity_priority(current), current.confidence, current.end - current.start)
    candidate_key = (entity_priority(candidate), candidate.confidence, candidate.end - candidate.start)
    return candidate if candidate_key > current_key else current


def deduplicate_entities(entities: list[Entity]) -> list[Entity]:
    selected: list[Entity] = []
    for entity in sorted(entities, key=lambda x: (x.start, -(x.end - x.start), -x.confidence)):
        duplicate = next((i for i, existing in enumerate(selected) if existing.start == entity.start and existing.end == entity.end and existing.text == entity.text), None)
        if duplicate is not None:
            selected[duplicate] = choose_entity(selected[duplicate], entity)
            continue
        overlap_idx = next((i for i, existing in enumerate(selected) if overlaps(existing, entity)), None)
        if overlap_idx is not None:
            selected[overlap_idx] = choose_entity(selected[overlap_idx], entity)
            continue
        selected.append(entity)
    return sorted(selected, key=lambda x: (x.start, x.end))


class HybridNerProvider(BaseNerProvider):
    name = 'hybrid'

    def __init__(self, natasha_provider: NatashaNerProvider | None = None, regex_provider: RegexRuleNerProvider | None = None):
        self.natasha_provider = natasha_provider or NatashaNerProvider()
        self.regex_provider = regex_provider or RegexRuleNerProvider()

    def extract(self, text: str) -> list[Entity]:
        return deduplicate_entities(self.natasha_provider.extract(text) + self.regex_provider.extract(text))


def build_provider() -> tuple[BaseNerProvider, str]:
    requested = os.getenv('NER_PROVIDER', 'hybrid').lower()
    regex_provider = RegexRuleNerProvider()
    if requested == 'regex':
        return regex_provider, 'regex'
    try:
        if requested == 'natasha':
            return NatashaNerProvider(), 'natasha'
        if requested == 'hybrid':
            return HybridNerProvider(regex_provider=regex_provider), 'hybrid'
        LOGGER.warning('Unknown NER_PROVIDER=%s, using hybrid', requested)
        return HybridNerProvider(regex_provider=regex_provider), 'hybrid'
    except Exception:
        LOGGER.exception('Failed to initialize Natasha NER provider, falling back to regex provider')
        return regex_provider, 'regex-fallback'


provider, active_provider = build_provider()


@app.get('/health')
def health():
    return {'status': 'ok', 'provider': active_provider}


@app.get('/ready')
def ready():
    return {'status': 'ready', 'provider': active_provider}


@app.post('/internal/ner/extract')
def extract(body: ExtractRequest, x_internal_service_token: str | None = Header(None)):
    if x_internal_service_token != INTERNAL:
        raise HTTPException(403, detail={'error': {'code': 'ACCESS_DENIED', 'message': 'Недостаточно прав', 'details': {}}})
    return {'entities': [entity.model_dump() for entity in provider.extract(body.text)]}
