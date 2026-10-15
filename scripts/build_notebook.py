"""Build the submitted notebook from the fully commented Python counterpart."""
from pathlib import Path
import re
import nbformat as nbf

root = Path(__file__).resolve().parents[1]
source = (root / 'agent_artist.py').read_text(encoding='utf-8')
chunks = re.split(r'^# %%( \[markdown\])?\s*\n', source, flags=re.MULTILINE)
notebook = nbf.v4.new_notebook()
notebook.metadata = {
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python', 'version': '3.12'},
}
notebook.cells.append(nbf.v4.new_markdown_cell('''# Лабораторная №1 — Агент-художник

**Археология будущего: следы присутствия**

Команда: Аршинов Иван, Барулева Кристина, Губенков Илья, Якушина Анна.

Этот ноутбук содержит полный код агентного цикла и сохранённые результаты.
По умолчанию он **не делает новых платных API-запросов**: показывает выполненный
эксперимент из `data/` и `docs/assets/`. Чтобы повторить генерацию, измените
`RUN_GENERATION` ниже. Контрольные точки переиспользуются; для нового независимого
эксперимента сохраните результаты отдельно и выберите пустой каталог данных.

Перед первым запуском установите зависимости:
```python
%pip install -r requirements.txt
# Для дополнительного локального рендерера:
# %pip install -r requirements-openweight.txt
```
Скопируйте `.env.sample` в `.env` и заполните выданные преподавателем значения.
Не публикуйте этот файл. Подробности: `README.md`, `REPORT.md`, `MODEL_CARD.md`.
'''))
for index in range(1, len(chunks), 2):
    markdown = chunks[index] is not None
    text = chunks[index + 1]
    if markdown:
        text = '\n'.join(line[2:] if line.startswith('# ') else line[1:] if line.startswith('#') else line
                         for line in text.rstrip().splitlines())
        notebook.cells.append(nbf.v4.new_markdown_cell(text))
    else:
        # The CLI guard is not needed in an interactive notebook.
        text = text.replace("if __name__ == '__main__' and '__file__' in globals():\n    main()", '')
        notebook.cells.append(nbf.v4.new_code_cell(text.strip()))

notebook.cells.extend([
    nbf.v4.new_markdown_cell('''## Запуск или просмотр сохранённого эксперимента

Генерация ограничена четырьмя работами и двумя версиями каждой. Критик оценивает
версии независимо, по одной рубрике. При равных баллах остаётся ранняя версия.
Генерация Yandex ART стохастична: точное совпадение пикселей при повторе не обещается.
Для SD-Turbo фиксируются seed и revision модели, но устройства и версии библиотек
тоже могут влиять на результат.'''),
    nbf.v4.new_code_cell('''RUN_GENERATION = False
RUN_OPENWEIGHT = False

if RUN_GENERATION:
    studio = Studio()
    generated = [make_painting(studio, brief, rounds=2) for brief in BRIEFS]
    if RUN_OPENWEIGHT:
        generate_openweight(generated[0], studio)

manifest = export_gallery()
print(f"Сохранённых картин: {len(manifest['works'])}")
print("Команда: " + ", ".join(TEAM))
'''),
    nbf.v4.new_markdown_cell('''## Коллекция и обратная связь

Ниже — фактические сохранённые версии и оценки VLM. Изменение суммы баллов
показывает только оценку этой модели; оно не доказывает объективный рост качества.
У каждого результата можно проверить исходный промпт и полный диалог в `data/`.
'''),
    nbf.v4.new_code_cell('''from IPython.display import Markdown, display

for work in manifest['works']:
    display(Markdown(f"### {work['title']}\\n{work['brief']['question']}"))
    rows = ["| Версия | Метафора | Композиция | Фактуры | Серия | Сумма | Выбор |",
            "|:--|--:|--:|--:|--:|--:|:--|"]
    for candidate in work['candidates']:
        score = candidate['review']['scores']
        chosen = 'финал' if candidate['version'] == work['selected_version'] else ''
        rows.append(f"| {candidate['version']} | {score['metaphor']} | {score['composition']} | "
                    f"{score['materiality']} | {score['series_fit']} | {candidate['review']['total']}/20 | {chosen} |")
    display(Markdown('\\n'.join(rows)))
    with Image.open(ASSETS / work['selected_image']) as picture:
        preview = picture.copy()
        preview.thumbnail((900, 900))
        display(preview)
    final = next(item for item in work['candidates'] if item['version'] == work['selected_version'])
    display(Markdown('**Наблюдения VLM:** ' + '; '.join(final['review']['observations'])))
    display(Markdown('**Замечания:** ' + '; '.join(final['review']['issues'])))
'''),
    nbf.v4.new_markdown_cell('## Пример настоящего диалога'),
    nbf.v4.new_code_cell('''if manifest['works']:
    for event in manifest['works'][0]['dialogue']:
        display(Markdown(f"#### {event['role']} · {event['stage']}\\nМодель: `{event['model']}`"))
        print(json.dumps(event.get('parsed'), ensure_ascii=False, indent=2))
'''),
    nbf.v4.new_markdown_cell('## Открытая модель с Hugging Face'),
    nbf.v4.new_code_cell('''comparison = manifest.get('openweight')
if comparison:
    print('Модель:', comparison['model'])
    print('Revision:', comparison['revision'])
    print('Seed:', comparison['seed'], 'Шагов:', comparison['steps'],
          'Разрешение:', comparison['size'], 'Устройство:', comparison['device'])
    with Image.open(ASSETS / comparison['image']) as picture:
        display(picture.copy())
    if comparison.get('review'):
        print('Субъективная оценка VLM:', comparison['review']['total'], '/ 20')
    print(comparison['comparison_note'])
else:
    print('SD-Turbo ещё не запускалась; дополнительных результатов не заявляем.')
'''),
    nbf.v4.new_markdown_cell('''## Выводы и ограничения

Разделение ролей даёт наблюдаемый протокол принятия решений: сначала обсуждается
смысл, затем композиция, затем видимое изображение. Текстовая самокритика не
заменяет VLM: последняя обнаруживает несовпадения замысла с реальным рендером.

Контур обратной связи не гарантирует улучшения. Поэтому сохранение альтернатив,
проверяемое правило выбора и журнал важнее заявления «агенты улучшили всё».
Оценки одного VLM зависимы от его модели и промпта; художник и критик используют
одну базовую Qwen с разными ролями и контекстом. Независимый человеческий разбор
не проводился в рамках этого автоматизированного прогона.

SD-Turbo показывает возможность заменить рендерер открытыми весами. Сравнение
ограничено различием разрешений, длины текстового окна и вычислительного бюджета.
Для строгого исследования нужны несколько запусков, одинаковые условия и
слепое человеческое оценивание. Подробные фактические результаты — в REPORT.md.
'''),
])
nbf.validate(notebook)
path = root / 'Agent_Artist.ipynb'
nbf.write(notebook, path)
print(f'Notebook built: {len(notebook.cells)} cells')
