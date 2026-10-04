/* Optional real-browser checks. Starts and removes its own local API process. */
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const {spawn,execFileSync} = require('node:child_process');
const {randomBytes} = require('node:crypto');
const root = path.resolve(__dirname,'..');
const sleep = ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function freePort(){const listener=net.createServer();await new Promise(resolve=>listener.listen(0,'127.0.0.1',resolve));const port=listener.address().port;await new Promise(resolve=>listener.close(resolve));return port;}
async function eventually(check){for(let i=0;i<50;i++){if(await check())return;await sleep(100);}throw new Error('Expected application state was not observed');}
(async()=>{
  const folder=fs.mkdtempSync(path.join(os.tmpdir(),'releaseops-browser-'));
  const token=randomBytes(32).toString('hex'),port=await freePort(),base=`http://127.0.0.1:${port}`;
  const python=process.env.PYTHON || (process.platform==='win32'?'python':'python3');
  const env={...process.env,API_TOKEN:token,APP_ENV:'ci',APP_VERSION:'browser-test',DATABASE_PATH:path.join(folder,'app.db')};
  const server=spawn(python,['-m','releaseops.server','--port',String(port),'--demo'],{cwd:root,env,stdio:'ignore'});
  let browser;
  try{
    await eventually(async()=>{try{return (await fetch(base+'/readyz')).ok;}catch{return false;}});
    const errors=[];
    browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{}),args:['--no-sandbox','--disable-dev-shm-usage']});
    const page=await browser.newPage({viewport:{width:1440,height:1080}});page.on('pageerror',error=>errors.push(error.message));
    await page.goto(base);await page.getByText('Ready',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Desktop overflow');
    await page.getByRole('button',{name:/New task/}).click();
    await page.locator('#operator-token').fill(token);
    await page.locator('#access-form button[type=submit]').click();
    await page.locator('#task-title').fill('Browser-tested release task');
    await page.locator('#task-owner').fill('DevOps team');
    await page.locator('#task-priority').selectOption('high');
    await page.locator('#task-form button[type=submit]').click();
    await page.getByText('Browser-tested release task',{exact:true}).waitFor();
    await page.getByRole('combobox',{name:'Status for Browser-tested release task'}).selectOption('done');
    await eventually(async()=>{const data=await (await fetch(base+'/api/state')).json();return data.tasks.some(item=>item.title==='Browser-tested release task'&&item.status==='done');});
    await page.getByRole('button',{name:/Report incident/}).first().click();
    await page.locator('#incident-title').fill('Browser-tested investigation');
    await page.locator('#incident-severity').selectOption('SEV2');
    await page.locator('#incident-form button[type=submit]').click();
    const row=page.locator('tbody tr').filter({hasText:'Browser-tested investigation'});
    await row.getByRole('button',{name:'Investigate',exact:true}).click();
    await row.getByRole('button',{name:'Resolve',exact:true}).click();
    await row.getByText('RESOLVED',{exact:true}).waitFor();
    execFileSync(python,[path.join(root,'scripts/monitor.py'),'--url',base,'--spool',path.join(folder,'spool.json'),'--once'],{env});
    await page.getByRole('button',{name:/Refresh/}).click();
    await page.getByText('100.00%',{exact:true}).waitFor();
    const output=path.join(root,'.local','browser');fs.mkdirSync(output,{recursive:true});
    await page.locator('#toast').waitFor({state:'hidden'});
    await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
    await page.getByRole('button',{name:'Releases',exact:true}).click();
    await page.getByRole('heading',{name:'Application releases',exact:true}).waitFor();
    await page.getByRole('button',{name:'Overview',exact:true}).click();
    await page.setViewportSize({width:390,height:844});await sleep(200);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'Mobile overflow');
    await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
    await page.locator('#mobile-access-button').click();
    assert.equal(await page.locator('#access-label').textContent(),'Unlock editing');
    assert.deepEqual(errors,[],'Unexpected browser JavaScript errors');
    console.log(JSON.stringify({result:'passed',checks:['dashboard loads','operator authentication','task creation and movement','incident investigation and resolution','real health chart','navigation','desktop/mobile overflow','operator lock','no JavaScript errors']},null,2));
  }finally{
    if(browser)await browser.close();
    server.kill();await new Promise(resolve=>{if(server.exitCode!==null)resolve();else server.once('exit',resolve);});
    fs.rmSync(folder,{recursive:true,force:true});
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
