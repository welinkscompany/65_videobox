import { chromium } from '@playwright/test';
const out = 'D:/AI_Workspace_louis_office_50/10_workspace/65_videobox/.worktrees/videobox-container-compatibility/artifacts/capcut-look';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
p.on('console', m => { if (m.type() === 'error') console.log('  콘솔오류:', m.text().slice(0, 100)); });
for (const [name, path] of [['01-홈','/'],['02-프로젝트','/projects'],['03-라이브러리','/library']]) {
  try {
    await p.goto('http://127.0.0.1:5173' + path, { waitUntil: 'networkidle', timeout: 45000 });
    await p.waitForTimeout(3000);
    await p.screenshot({ path: `${out}/${name}.png` });
    console.log('찍음', name, '|', (await p.title()) || '(제목없음)');
  } catch (e) { console.log('실패', name, String(e).split('\n')[0].slice(0,110)); }
}
await b.close();
