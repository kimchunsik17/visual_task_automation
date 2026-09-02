// 디자인 프리셋 4종을 캔버스(elements) 기반으로 변환한다.
// html/css 는 편집기와 같은 직렬화기(formatCanvas.serializeElements)로 만들므로,
// 스튜디오에서 열어 요소 하나만 움직여 저장해도 코드 모양이 흔들리지 않는다.
// 실행: frontend 디렉토리에서 `node scripts/convert_design_presets.mjs`
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { serializeElements } from '../src/formatCanvas.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const DIR = path.join(ROOT, 'document_formats');

const text = (id, text, rest) => ({ id, kind: 'text', bold: false, align: 'left', color: 'textColor', lineHeight: 1.45, text, ...rest });
const image = (id, field, rest) => ({ id, kind: 'image', field, radius: 12, ...rest });
const box = (id, rest) => ({ id, kind: 'box', borderColor: 'primaryColor', borderWidth: 1, background: '', radius: 0, ...rest });

const PRESETS = {
  'event-poster.json': [
    text('host', '{{hostName}}', { x: 56, y: 52, w: 400, h: 30, fontSize: 15, bold: true, color: 'primaryColor', letterSpacing: '.08em' }),
    image('hero', 'mainImage', { x: 56, y: 100, w: 682, h: 330, radius: 18 }),
    text('title', '{{eventTitle}}', { x: 56, y: 460, w: 682, h: 150, fontSize: 60, bold: true, lineHeight: 1.16 }),
    text('tagline', '{{tagline}}', { x: 56, y: 616, w: 682, h: 40, fontSize: 26, bold: true, color: 'primaryColor' }),
    text('desc', '{{descriptionText}}', { x: 56, y: 670, w: 682, h: 168, fontSize: 17, color: 'mutedColor', lineHeight: 1.7 }),
    text('meta1', '일시  {{dateTime}}', { x: 56, y: 880, w: 682, h: 34, fontSize: 20, bold: true }),
    text('meta2', '장소  {{place}}', { x: 56, y: 924, w: 682, h: 34, fontSize: 20, bold: true }),
    text('contact', '{{contactInfo}}', { x: 56, y: 1030, w: 682, h: 40, fontSize: 15, color: 'mutedColor' }),
  ],
  'tri-fold-pamphlet.json': [
    text('p1title', '{{panel1Title}}', { x: 34, y: 44, w: 306, h: 34, fontSize: 22, bold: true, color: 'primaryColor' }),
    text('p1body', '{{panel1Body}}', { x: 34, y: 92, w: 306, h: 620, fontSize: 14, lineHeight: 1.75 }),
    text('p2title', '{{panel2Title}}', { x: 408, y: 44, w: 306, h: 34, fontSize: 22, bold: true, color: 'primaryColor' }),
    text('p2body', '{{panel2Body}}', { x: 408, y: 92, w: 306, h: 560, fontSize: 14, lineHeight: 1.75 }),
    text('contact', '{{contact}}', { x: 408, y: 700, w: 306, h: 40, fontSize: 14, bold: true, color: 'mutedColor' }),
    text('brand', '{{brandName}}', { x: 782, y: 150, w: 306, h: 26, fontSize: 15, bold: true, color: 'primaryColor', align: 'center', letterSpacing: '.12em' }),
    image('cover', 'coverImage', { x: 782, y: 196, w: 306, h: 280, radius: 14 }),
    text('headline', '{{headline}}', { x: 782, y: 500, w: 306, h: 130, fontSize: 32, bold: true, align: 'center', lineHeight: 1.25 }),
  ],
  'card-news.json': [
    text('brand', '{{brandName}}', { x: 64, y: 60, w: 500, h: 32, fontSize: 22, bold: true, color: 'primaryColor', letterSpacing: '.12em' }),
    text('page', '{{pageLabel}}', { x: 816, y: 60, w: 200, h: 32, fontSize: 20, color: 'mutedColor', align: 'right' }),
    image('hero', 'mainImage', { x: 64, y: 120, w: 952, h: 370, radius: 22 }),
    text('title', '{{title}}', { x: 64, y: 520, w: 952, h: 155, fontSize: 58, bold: true, lineHeight: 1.2 }),
    text('highlight', '{{highlight}}', { x: 64, y: 692, w: 952, h: 44, fontSize: 26, bold: true, color: 'primaryColor' }),
    text('body', '{{body}}', { x: 64, y: 770, w: 952, h: 240, fontSize: 26, color: 'mutedColor', lineHeight: 1.65 }),
  ],
  'certificate-award.json': [
    box('frame', { x: 34, y: 34, w: 1055, h: 726, borderWidth: 3 }),
    box('frameInner', { x: 46, y: 46, w: 1031, h: 702, borderWidth: 1 }),
    text('number', '{{certNumber}}', { x: 90, y: 78, w: 300, h: 26, fontSize: 16, color: 'mutedColor' }),
    text('title', '{{certTitle}}', { x: 62, y: 140, w: 999, h: 72, fontSize: 54, bold: true, align: 'center', letterSpacing: '.5em' }),
    text('who', '{{recipientOrg}}   {{recipientName}}', { x: 62, y: 272, w: 999, h: 46, fontSize: 30, bold: true, align: 'center' }),
    text('course', '{{courseName}}', { x: 62, y: 330, w: 999, h: 32, fontSize: 21, bold: true, color: 'primaryColor', align: 'center' }),
    text('body', '{{bodyText}}', { x: 162, y: 392, w: 799, h: 160, fontSize: 19, align: 'center', lineHeight: 1.9 }),
    text('date', '{{issueDate}}', { x: 62, y: 620, w: 999, h: 28, fontSize: 18, align: 'center' }),
    text('issuer', '{{issuerName}} (인)', { x: 62, y: 664, w: 999, h: 36, fontSize: 24, bold: true, align: 'center', letterSpacing: '.08em' }),
  ],
};

for (const [file, elements] of Object.entries(PRESETS)) {
  const fullPath = path.join(DIR, file);
  const spec = JSON.parse(readFileSync(fullPath, 'utf8'));
  const { html, css } = serializeElements(elements);
  spec.design = {
    width: spec.design.width,
    height: spec.design.height,
    theme: spec.design.theme,
    elements,
    html,
    css,
  };
  writeFileSync(fullPath, JSON.stringify(spec, null, 2) + '\n', 'utf8');
  console.log(`${file}: ${elements.length} elements, css ${css.length}B`);
}
