# %% [markdown]
# # Археология будущего
# Лабораторная №1 «Агент-художник». Команда: Аршинов Иван, Барулева Кристина,
# Губенков Илья, Якунина Анна.
#
# Система разделяет замысел, визуальное исполнение и оценку: два независимых
# LLM-агента общаются текстом, затем VLM-критик рассматривает реальную картину.
# Все запросы, ответы, промпты, оценки и версии сохраняются на диск.

# %%
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

ROOT = Path(__file__).resolve().parent if '__file__' in globals() else Path.cwd()
DATA = ROOT / 'data'
ASSETS = ROOT / 'docs' / 'assets'
TEAM = ['Аршинов Иван', 'Барулева Кристина', 'Губенков Илья', 'Якунина Анна']
SERIES = 'Археология будущего'
STYLE = (
    'A coherent series of conceptual fine-art paintings: a museum of intangible '
    'digital habits in the year 2126. Painterly material textures, oxidised copper, '
    'deep petrol and ultramarine, warm amber light, restrained ivory highlights. '
    'One legible metaphor per painting, generous negative space, visual hierarchy, '
    'quiet atmosphere. Not a literal computer illustration. No written words, '
    'no letters, no logos, no screens, no neon cyberpunk, no robots.'
)
BRIEFS = [
    {'id': '01-notification', 'title': 'Последнее уведомление',
     'question': 'Как выглядит потребность постоянно быть замеченным, когда отвечать уже некому?',
     'seed_idea': 'Археологический след уведомления: немой колокол и одно уцелевшее свечение.'},
    {'id': '02-unread', 'title': 'Сад непрочитанных сообщений',
     'question': 'Может ли невысказанное прорасти, если его так и не прочитали?',
     'seed_idea': 'Непрочитанные сообщения стали семенами; хрупкий сад хранит несовершившийся разговор.'},
    {'id': '03-cloud', 'title': 'Облачный гербарий',
     'question': 'Что остаётся от обещания хранить воспоминания вечно?',
     'seed_idea': 'Облачная память как гербарий: высушенные облака между музейными стёклами.'},
    {'id': '04-routes', 'title': 'Река отменённых маршрутов',
     'question': 'Где живут места, до которых мы решили не дойти?',
     'seed_idea': 'Несостоявшиеся маршруты собираются в русло, текущее через безлюдный музей.'},
]

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)

def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))

def extract_json(text: str) -> dict:
    """Allow Markdown fences, but reject missing/invalid JSON rather than inventing data."""
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end < start:
        raise ValueError('The agent did not return a JSON object.')
    # Some compatible backends emit literal tabs/newlines inside strings.
    # Accept these characters while retaining the exact raw response in the log.
    value = json.loads(text[start:end + 1], strict=False)
    if not isinstance(value, dict):
        raise ValueError('Expected a JSON object.')
    return value

# %% [markdown]
# ## Настройка API и роли
# `.env` размещается рядом с ноутбуком либо задаётся через `DOTENV_PATH`.
# Значения не печатаются и не попадают в журнал. Responses API и Image Generation
# API вызываются через совместимый клиент. История передаётся явно: это делает
# независимые роли и контекст каждого решения видимыми и воспроизводимыми.

# %%
class Studio:
    def __init__(self) -> None:
        load_dotenv(Path(os.environ.get('DOTENV_PATH', ROOT / '.env')), override=False)
        self.folder = os.environ.get('folder_id') or os.environ.get('FOLDER_ID')
        self.key = os.environ.get('api_key') or os.environ.get('API_KEY')
        if not self.folder or not self.key:
            raise RuntimeError('Add folder_id and api_key to .env; see .env.sample.')
        self.models = {
            'curator': os.environ.get('CURATOR_MODEL', 'deepseek-v4.1-flash'),
            'artist': os.environ.get('ARTIST_MODEL', 'qwen3.6-35b-a3b/latest'),
            'critic': os.environ.get('CRITIC_MODEL', 'qwen3.6-35b-a3b/latest'),
            'image': os.environ.get('IMAGE_MODEL', 'aliceai-image-art-3.0/latest'),
        }
        self.client = OpenAI(base_url='https://ai.api.cloud.yandex.net/v1',
                             api_key=self.key, project=self.folder,
                             timeout=240, max_retries=2)

    def sanitize(self, value: Any) -> Any:
        if isinstance(value, str):
            return value.replace(self.key, '[API_KEY]').replace(self.folder, '[FOLDER_ID]')
        if isinstance(value, dict):
            return {key: self.sanitize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.sanitize(item) for item in value]
        return value

    def ask(self, work: dict, role: str, stage: str, instructions: str,
            prompt: str, image: Path | None = None) -> dict:
        """Checkpoint every successful turn; a resumed run reuses it, not the API."""
        for event in work['dialogue']:
            if event['stage'] != stage:
                continue
            try:
                parsed = extract_json(event['output_text'])
                if role == 'critic':
                    parsed = validated_review(parsed)
            except (ValueError, json.JSONDecodeError):
                continue
            event['parsed'] = parsed
            checkpoint(work)
            return parsed
        model = self.models[role]
        content = [{'type': 'input_text', 'text': prompt}]
        if image:
            with Image.open(image) as source:
                source = source.convert('RGB')
                source.thumbnail((1024, 1024))
                buffer = io.BytesIO()
                source.save(buffer, format='JPEG', quality=90)
            encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
            content.append({'type': 'input_image',
                            'image_url': f'data:image/jpeg;base64,{encoded}', 'detail': 'auto'})
        started = time.monotonic()
        for attempt in range(2):
            # Explicit role instructions and transcript delimiters avoid mixing
            # instructions from one agent with the controller's protocol.
            request_prompt = prompt if attempt == 0 else prompt + '\nВерни только корректный JSON без Markdown.'
            request_content = [dict(content[0], text=request_prompt), *content[1:]]
            reasoning_options = {'reasoning': {'effort': 'none'}} if 'qwen3.6' in model else {}
            output_options = {}
            if role == 'critic':
                review_schema = {
                    'type': 'object', 'additionalProperties': False,
                    'properties': {
                        key: {'type': 'array', 'items': {'type': 'string'}}
                        for key in ('observations', 'strengths', 'issues', 'changes')
                    },
                    'required': ['observations', 'scores', 'strengths', 'issues', 'changes'],
                }
                review_schema['properties']['scores'] = {
                    'type': 'object', 'additionalProperties': False,
                    'properties': {key: {'type': 'integer', 'minimum': 1, 'maximum': 5}
                                   for key in ('metaphor', 'composition', 'materiality', 'series_fit')},
                    'required': ['metaphor', 'composition', 'materiality', 'series_fit'],
                }
                output_options = {'text': {'format': {'type': 'json_schema', 'name': 'visual_review',
                                                     'schema': review_schema, 'strict': True}}}
            response = self.client.responses.create(
                model=f'gpt://{self.folder}/{model}',
                instructions=instructions + '\nОтвечай по-русски, кроме image_prompt. Формат: JSON.',
                input=[{'role': 'user', 'content': request_content}],
                max_output_tokens=4096,
                **reasoning_options,
                **output_options,
            )
            text = response.output_text or ''
            event = {
                'stage': stage, 'role': role, 'model': model, 'timestamp': utcnow(),
                'instructions': instructions, 'input_text': request_prompt,
                'image': image.name if image else None, 'output_text': text,
                'response_id': response.id, 'status': response.status,
                'elapsed_s': round(time.monotonic() - started, 2),
                'usage': response.usage.model_dump() if response.usage else None,
                'response_format': output_options.get('text'),
            }
            try:
                event['parsed'] = extract_json(text)
                if role == 'critic':
                    event['parsed'] = validated_review(event['parsed'])
            except (ValueError, json.JSONDecodeError):
                event['parsed'] = None
            work['dialogue'].append(self.sanitize(event))
            checkpoint(work)
            if event['parsed'] is not None:
                return event['parsed']
        raise ValueError(f'{role}/{stage}: two invalid JSON responses; see saved dialogue.')

    def draw(self, work: dict, prompt: str, version: int) -> dict:
        for candidate in work['candidates']:
            if candidate['version'] == version and (ASSETS / candidate['image']).exists():
                return candidate
        started = time.monotonic()
        # Image API supports seeded generation through extra_body in some
        # backends, but this run does not claim deterministic Yandex generation.
        response = self.client.images.generate(
            model=f'art://{self.folder}/{self.models["image"]}',
            prompt=prompt, size='1536x1024', n=1,
        )
        if not response.data or not response.data[0].b64_json:
            raise RuntimeError('Image API returned no base64 image.')
        image_bytes = base64.b64decode(response.data[0].b64_json, validate=True)
        ASSETS.mkdir(parents=True, exist_ok=True)
        name = f'{work["id"]}-v{version}.png'
        # Decode/verify the service result before committing an asset.
        with Image.open(io.BytesIO(image_bytes)) as image:
            actual_size = list(image.size)
            image.convert('RGB').save(ASSETS / name, format='PNG')
        candidate = {
            'version': version, 'image': name, 'prompt': prompt,
            'model': self.models['image'], 'timestamp': utcnow(),
            'requested_size': [1536, 1024], 'actual_size': actual_size,
            'elapsed_s': round(time.monotonic() - started, 2),
            'sha256': hashlib.sha256((ASSETS / name).read_bytes()).hexdigest(),
        }
        work['candidates'].append(candidate)
        checkpoint(work)
        return candidate

CURATOR = '''Ты — куратор воображаемого музея 2126 года. Твоя задача —
развивать ясную, небанальную метафору цифровой привычки через материальный
экспонат. Не пиши общих похвал, требуй конкретного визуального решения.
Сохраняй исходное название и тему. Не добавляй печатный текст в картину.'''
ARTIST = '''Ты — художник и визуальный режиссёр. Превращай обсуждение с
куратором в выполнимую сцену для генератора изображений. Выбирай один
главный объект, пространственные отношения, свет и материал. Не пересказывай
абстракции, а показывай их через наблюдаемые детали. Сохраняй стиль серии.
Поле image_prompt: английский промпт до 150 слов, включая ограничения.'''
CRITIC = '''Ты — независимый VLM-критик. Оценивай ТОЛЬКО приложенное
изображение, а не обещания промпта. Сначала перечисли реально видимые детали.
Не выдумывай текст, объекты и улучшение. По каждому критерию поставь целое
число 1–5: metaphor (метафора различима без пояснения), composition
(фокус и пространство), materiality (фактуры и свет), series_fit (единый
живописный музейный стиль). Укажи конкретные недостатки и 2–3 визуально
исполнимых изменения. Баллы — субъективная рубрика, не объективная метрика.'''

def checkpoint(work: dict) -> None:
    save_json(DATA / f'{work["id"]}.json', work)

def context(work: dict) -> str:
    return json.dumps({
        'brief': work['brief'], 'series_style': STYLE,
        'discussion': [
            {'role': event['role'], 'stage': event['stage'], 'answer': event['parsed']}
            for event in work['dialogue'] if event.get('parsed') is not None
        ],
    }, ensure_ascii=False)

def validated_review(value: dict) -> dict:
    scores = value.get('scores', {})
    for key in ('metaphor', 'composition', 'materiality', 'series_fit'):
        score = scores.get(key)
        if type(score) is not int or not 1 <= score <= 5:
            raise ValueError(f'Invalid VLM score: {key}={score!r}')
    if not isinstance(value.get('observations'), list) or not value['observations']:
        raise ValueError('Review must contain visible observations.')
    if not isinstance(value.get('changes'), list):
        raise ValueError('Review must contain a changes list.')
    return dict(value, total=sum(scores[key] for key in
                ('metaphor', 'composition', 'materiality', 'series_fit')))

# %% [markdown]
# ## Агентный цикл
# Куратор → художник → возражения куратора → первый промпт → изображение →
# VLM-критика → ответ художника → вторая версия → повторная VLM-критика.
#
# Правило выбора задано заранее: максимальная сумма четырёх оценок 1–5;
# при равенстве сохраняется ранняя версия. Повторная генерация не обязана
# улучшить картину. Оценки, изменения и фактический выбор публикуются вместе.
# Две версии — бюджетное ограничение, а не эвристика сходимости.

# %%
def make_painting(studio: Studio, brief: dict, rounds: int = 2) -> dict:
    path = DATA / f'{brief["id"]}.json'
    work = read_json(path) if path.exists() else {
        'id': brief['id'], 'title': brief['title'], 'brief': brief,
        'created_at': utcnow(), 'dialogue': [], 'candidates': [],
    }
    print(f'[{work["id"]}] curator and artist', flush=True)
    studio.ask(work, 'curator', 'curator-concept', CURATOR,
               context(work) + '\nПредложи экспонат. JSON: {"concept": str, "meaning": str, '
               '"visual_motifs": [str], "avoid": [str]}.')
    studio.ask(work, 'artist', 'artist-proposal', ARTIST,
               context(work) + '\nОтветь куратору своим решением. JSON: '
               '{"response_to_curator": str, "composition": str, "image_prompt": str}.')
    studio.ask(work, 'curator', 'curator-challenge', CURATOR,
               context(work) + '\nОспорь одно слабое место предложения художника. JSON: '
               '{"challenge": str, "must_preserve": [str], "specific_adjustment": str}.')
    for version in range(1, rounds + 1):
        stage = f'artist-prompt-v{version}'
        instruction = ('Учти замечание куратора и зафиксируй первый промпт.' if version == 1
                       else 'Ответь на замечания VLM по предыдущей версии. Исправь '
                       'наблюдаемые проблемы, сохрани удачные элементы и метафору.')
        proposal = studio.ask(work, 'artist', stage, ARTIST,
                              context(work) + '\n' + instruction + '\nJSON: '
                              '{"response_to_feedback": str, "changes": [str], "image_prompt": str}.')
        prompt = proposal.get('image_prompt')
        if not isinstance(prompt, str) or len(prompt) < 60:
            raise ValueError(f'{stage}: missing substantive image prompt')
        print(f'[{work["id"]}] generate v{version}', flush=True)
        candidate = studio.draw(work, prompt, version)
        if 'review' not in candidate:
            review = studio.ask(work, 'critic', f'critic-v{version}', CRITIC,
                                'Тема и стиль (это намерение, не описание факта):\n' +
                                json.dumps({'brief': brief, 'style': STYLE}, ensure_ascii=False) +
                                '\nРассмотри приложенную картину. Не сравнивай с невидимой '
                                'прошлой версией. JSON: {"observations": [str], '
                                '"scores": {"metaphor": int, "composition": int, '
                                '"materiality": int, "series_fit": int}, "strengths": [str], '
                                '"issues": [str], "changes": [str]}.',
                                image=ASSETS / candidate['image'])
            candidate['review'] = validated_review(review)
            checkpoint(work)
        print(f'[{work["id"]}] v{version}: {candidate["review"]["total"]}/20', flush=True)
    judged = [candidate for candidate in work['candidates'] if 'review' in candidate]
    best = max(judged, key=lambda candidate: (candidate['review']['total'], -candidate['version']))
    work['selected_version'] = best['version']
    work['selected_image'] = best['image']
    work['selection_rule'] = 'max(sum of four 1–5 VLM scores); earliest version wins ties'
    work['completed_at'] = utcnow()
    checkpoint(work)
    return work

# %% [markdown]
# ## Дополнительный открытый рендерер
# SD-Turbo (stabilityai/sd-turbo, Hugging Face, лицензия в MODEL_CARD.md)
# используется локально через Diffusers. Она получает тот же финальный промпт
# первого экспоната. Фиксируем seed, число шагов, разрешение и устройство.
# Промпт длиннее окна CLIP будет обрезан самим токенизатором; сохраняем также
# фактически декодированный текст. Вывод не подменяет результат Yandex ART.

# %%
def generate_openweight(work: dict, studio: Studio | None = None) -> dict:
    metadata_path = DATA / 'openweight.json'
    def attach_review(metadata: dict) -> dict:
        if studio is not None and 'review' not in metadata:
            review = studio.ask(work, 'critic', 'critic-openweight', CRITIC,
                                'Оцени приложенный вариант по теме «' + work['title'] +
                                '». Стиль: ' + STYLE + '\nJSON: {"observations": [str], '
                                '"scores": {"metaphor": int, "composition": int, "materiality": int, '
                                '"series_fit": int}, "strengths": [str], "issues": [str], "changes": [str]}.',
                                image=ASSETS / metadata['image'])
            metadata['review'] = validated_review(review)
        save_json(metadata_path, metadata)
        return metadata
    if metadata_path.exists():
        metadata = read_json(metadata_path)
        if (ASSETS / metadata['image']).exists():
            return attach_review(metadata)
    import torch
    from diffusers import AutoPipelineForText2Image
    from huggingface_hub import model_info

    model_id = 'stabilityai/sd-turbo'
    revision = model_info(model_id).sha
    device = 'mps' if torch.backends.mps.is_available() else ('cuda' if torch.cuda.is_available() else 'cpu')
    # float32 on MPS avoids device-dependent half precision black-image failures.
    dtype = torch.float16 if device == 'cuda' else torch.float32
    pipe = AutoPipelineForText2Image.from_pretrained(
        model_id, revision=revision, torch_dtype=dtype, use_safetensors=True, variant='fp16',
    ).to(device)
    pipe.enable_attention_slicing()
    candidate = next(item for item in work['candidates'] if item['version'] == work['selected_version'])
    prompt = candidate['prompt']
    seed = 2126
    generator = torch.Generator(device='cpu').manual_seed(seed)
    started = time.monotonic()
    image = pipe(prompt=prompt, num_inference_steps=4, guidance_scale=0.0,
                 width=512, height=512, generator=generator).images[0]
    image_name = '01-notification-sd-turbo.png'
    image.save(ASSETS / image_name)
    tokens = pipe.tokenizer(prompt, truncation=True,
                           max_length=pipe.tokenizer.model_max_length).input_ids
    metadata = {
        'model': model_id, 'revision': revision, 'license': 'Stability AI Community License',
        'prompt': prompt, 'effective_prompt': pipe.tokenizer.decode(tokens),
        'seed': seed, 'steps': 4, 'guidance_scale': 0.0, 'size': [512, 512],
        'device': device, 'dtype': str(dtype), 'image': image_name,
        'elapsed_s': round(time.monotonic() - started, 2), 'timestamp': utcnow(),
        'sha256': hashlib.sha256((ASSETS / image_name).read_bytes()).hexdigest(),
        'comparison_note': 'Same submitted prompt; different resolution, tokenizer and compute. Not a controlled quality benchmark.',
    }
    save_json(metadata_path, metadata)
    return attach_review(metadata)

# %% [markdown]
# ## Экспорт и воспроизводимость
# Сайт читает предварительно подготовленный публичный JSON с реальными
# диалогами. В нём нет ключей или base64-вложений. Набор результатов можно
# изучить без API и без подключения к облаку. Повторный запуск использует
# контрольные точки; для новой независимой серии нужен отдельный каталог data.

# %%
def export_gallery() -> dict:
    works = [read_json(DATA / f'{brief["id"]}.json') for brief in BRIEFS
             if (DATA / f'{brief["id"]}.json').exists()]
    complete = [work for work in works if work.get('selected_image')]
    for work in complete:
        for candidate in work['candidates']:
            if 'actual_size' not in candidate:
                with Image.open(ASSETS / candidate['image']) as picture:
                    candidate['actual_size'] = list(picture.size)
                candidate['requested_size'] = [1536, 1024]
        checkpoint(work)
    manifest = {
        'title': SERIES, 'subtitle': 'Следы присутствия · музей цифровых привычек, 2126',
        'team': TEAM, 'style': STYLE, 'exported_at': utcnow(),
        'works': complete,
        'openweight': read_json(DATA / 'openweight.json') if (DATA / 'openweight.json').exists() else None,
        'evaluation_note': 'Оценки принадлежат VLM-критику. Это субъективная рубрика, не независимая экспертиза.',
    }
    save_json(ROOT / 'docs' / 'gallery.json', manifest)
    lines = ['# Реальные диалоги агентов', '', 'Журнал автоматически экспортирован из ответов API.', '']
    for work in complete:
        lines.extend([f'## {work["title"]}', '', f'Выбрана версия {work["selected_version"]}.', ''])
        for event in work['dialogue']:
            lines.extend([f'### {event["stage"]} · {event["role"]}', '',
                          f'Модель: `{event["model"]}`. ID ответа: `{event["response_id"]}`.', '',
                          '```json', json.dumps(event.get('parsed'), ensure_ascii=False, indent=2), '```', ''])
    (ROOT / 'DIALOGUES.md').write_text('\n'.join(lines), encoding='utf-8')
    return manifest

def main() -> None:
    parser = argparse.ArgumentParser(description='Multi-agent artist: Yandex Responses + Image API')
    parser.add_argument('--only', choices=[brief['id'] for brief in BRIEFS])
    parser.add_argument('--rounds', type=int, choices=(1, 2), default=2)
    parser.add_argument('--openweight', action='store_true')
    parser.add_argument('--export-only', action='store_true')
    args = parser.parse_args()
    if args.export_only:
        manifest = export_gallery()
        print(f'Exported {len(manifest["works"])} paintings.')
        return
    studio = Studio()
    works = []
    for brief in BRIEFS:
        if args.only is None or args.only == brief['id']:
            works.append(make_painting(studio, brief, args.rounds))
            export_gallery()
    if args.openweight:
        first = read_json(DATA / f'{BRIEFS[0]["id"]}.json')
        generate_openweight(first, studio)
    manifest = export_gallery()
    print(f'Complete: {len(manifest["works"])} paintings.', flush=True)

if __name__ == '__main__' and '__file__' in globals():
    main()
