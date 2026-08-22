import { chromium } from '@playwright/test';
const out = 'D:/AI_Workspace_louis_office_50/10_workspace/65_videobox/.worktrees/videobox-container-compatibility/artifacts/capcut-look';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 } });
for (const [name, path] of [['04-편집기','/projects/my-project/editing'],['05-재료','/projects/my-project/media']]) {
  try {
    await p.goto('http://127.0.0.1:5173' + path, { waitUntil: 'networkidle', timeout: 60000 });
    await p.waitForTimeout(4000);
    await p.screenshot({ path: `${out}/${name}.png` });
    console.log('찍음', name);
  } catch (e) { console.log('실패', name, String(e).split('\n')[0].slice(0,100)); }
}
await b.close();
