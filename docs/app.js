'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const el = (tag, attrs = {}, text = '') => {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  if (text) node.textContent = text;
  return node;
};
const roleNames = {curator: 'Куратор', artist: 'Художник', critic: 'VLM-критик'};
const scoreNames = {metaphor: 'Метафора', composition: 'Композиция', materiality: 'Фактуры', series_fit: 'Единство серии'};
const stageNames = {'curator-concept':'Замысел', 'artist-proposal':'Визуальное решение', 'curator-challenge':'Возражение куратора', 'artist-prompt-v1':'Первый промпт', 'critic-v1':'Разбор первой версии', 'artist-prompt-v2':'Ответ на критику', 'critic-v2':'Разбор второй версии', 'critic-openweight':'Разбор SD-Turbo'};
const lightbox = $('#lightbox');
$('#close-lightbox').addEventListener('click', () => lightbox.close());
lightbox.addEventListener('click', event => { if (event.target === lightbox) lightbox.close(); });
function showImage(src, title) {
  $('img', lightbox).src = src; $('img', lightbox).alt = title;
  $('p', lightbox).textContent = title; lightbox.showModal();
}
function details(label, body) {
  const wrapper = el('details'); wrapper.append(el('summary', {}, label), body); return wrapper;
}
function reviewNode(review) {
  const wrapper = el('div', {class: 'review-body'});
  for (const [key, title] of [['observations','Что критик действительно увидел'],['strengths','Сильные стороны'],['issues','Замечания'],['changes','Предложенные изменения']]) {
    if (!Array.isArray(review[key]) || !review[key].length) continue;
    wrapper.append(el('h4', {}, title)); const list = el('ul');
    for (const item of review[key]) list.append(el('li', {}, String(item)));
    wrapper.append(list);
  }
  return wrapper;
}
function renderPainting(work, index) {
  const article = el('article', {class:'painting', id:work.id, 'aria-labelledby':work.id+'-title'});
  const visual = el('div', {class:'painting-visual'});
  const imageButton = el('button', {type:'button',class:'image-button','aria-label':'Увеличить: '+work.title});
  const image = el('img', {loading:'lazy',width:'1536',height:'1024',alt:work.title});
  imageButton.append(image, el('span',{class:'zoom-hint'},'Открыть картину ↗'));
  const caption = el('div',{class:'image-caption'}); visual.append(imageButton,caption);
  imageButton.addEventListener('click', () => showImage(image.src, work.title));
  const info = el('div',{class:'painting-info'});
  info.append(el('p',{class:'painting-number'},'ЭКСПОНАТ '+String(index+1).padStart(2,'0')+' / 2126'),
    el('h3',{class:'painting-title',id:work.id+'-title'},work.title),
    el('p',{class:'painting-question'},work.brief.question));
  const concept = work.dialogue.find(event=>event.stage==='curator-concept' && event.parsed)?.parsed;
  const meaning=concept?.meaning || work.brief.seed_idea;
  const lead=(meaning.match(/[^.!?]+[.!?]+(?:\s|$)/g)||[meaning]).slice(0,2).join('').trim();
  info.append(el('p',{class:'painting-meaning'},lead));
  const versions = el('div',{class:'versions','aria-label':'Версии картины'});
  const selection = el('p',{class:'selection-note'});
  const scoreRow = el('div',{class:'score-row'});
  const reviewBody = el('div');
  const prompt = el('pre');
  const buttons = [];
  function select(candidate) {
    image.src='assets/'+candidate.image;
    caption.replaceChildren(el('span',{},candidate.model),el('span',{},'Версия '+candidate.version+' / '+candidate.review.total+' из 20'));
    selection.textContent='Финальной выбрана версия '+work.selected_version+'. '+
      (candidate.version===work.selected_version?'Сейчас показан финал.':'Сейчас показана альтернативная версия.');
    buttons.forEach(([button, version])=>button.setAttribute('aria-pressed',String(version===candidate.version)));
    scoreRow.replaceChildren();
    for (const [key,label] of Object.entries(scoreNames)) {
      const node=el('div'); node.append(el('strong',{},String(candidate.review.scores[key])+'/5'),el('span',{},label)); scoreRow.append(node);
    }
    reviewBody.replaceChildren(reviewNode(candidate.review)); prompt.textContent=candidate.prompt;
  }
  for (const candidate of work.candidates) {
    const button=el('button',{type:'button',class:'version-button','aria-pressed':'false'},
      'Версия '+candidate.version+(candidate.version===work.selected_version?' · финал':''));
    button.addEventListener('click',()=>select(candidate)); versions.append(button); buttons.push([button,candidate.version]);
  }
  const dialogue = el('div');
  for (const event of work.dialogue) {
    const block=el('section',{class:'dialogue-event'});
    block.append(el('h4',{},roleNames[event.role]+' · '+(stageNames[event.stage]||event.stage)),
      el('small',{},event.model+' · '+event.response_id),
      el('pre',{},JSON.stringify(event.parsed || event.output_text,null,2)));
    dialogue.append(block);
  }
  info.append(versions,selection,scoreRow,details('Полный кураторский замысел',el('p',{class:'review-body'},meaning)),details('Визуальная критика этой версии',reviewBody),
    details('Промпт этой версии',prompt),details('Полный диалог агентов · '+work.dialogue.length+' реплик',dialogue));
  article.append(visual,info);select(work.candidates.find(candidate=>candidate.version===work.selected_version));
  return article;
}
async function boot() {
  try {
    const response=await fetch('gallery.json'); if(!response.ok) throw new Error('HTTP '+response.status);
    const data=await response.json();
    if(!data.works.length) throw new Error('Коллекция ещё не сгенерирована.');
    $('#hero-image').src='assets/'+data.works[0].selected_image;
    $('#hero-image').alt=data.works[0].title;
    $('#paintings').replaceChildren(...data.works.map(renderPainting));
    $('#team-list').replaceChildren(...data.team.map(name=>el('li',{},name)));
    if(data.openweight) {
      $('#openweight').hidden=false;
      const first=data.works[0];
      const original=first.candidates.find(candidate=>candidate.version===first.selected_version);
      for(const [filename,title] of [[first.selected_image,'Yandex ART · '+original.review.total+'/20'],
        [data.openweight.image,'SD-Turbo · '+(data.openweight.review ? data.openweight.review.total+'/20' : 'открытые веса')]]) {
        const figure=el('figure');const img=el('img',{src:'assets/'+filename,alt:title,loading:'lazy',width:'512',height:'512'});
        figure.append(img,el('figcaption',{},title));$('#comparison').append(figure);
      }
      const {prompt,effective_prompt,model,revision,seed,steps,guidance_scale,size,device,dtype,elapsed_s}=data.openweight;
      $('#openweight-data').textContent=JSON.stringify({model,revision,seed,steps,guidance_scale,size,device,dtype,elapsed_s,prompt,effective_prompt},null,2);
    }
  } catch(error) {
    $('#paintings').replaceChildren(el('p',{class:'loading'},'Не удалось загрузить коллекцию. Откройте сайт через HTTP или GitHub Pages. '+error.message));
  }
}
boot();
