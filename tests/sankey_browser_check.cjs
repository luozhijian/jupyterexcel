const {chromium} = require('playwright');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1100, height: 600}});
    await page.setContent('<body style="margin:0;background:white"></body>');
    await page.addScriptTag({path:'jupyterexcel/addin_template/sankey.bundle.js'});
    const result = await page.evaluate(() => {
      const graph = JupyterExcelCharts.graphFromRows([
        ['Source','Target','Value'], ['Revenue','Operations',60], ['Revenue','Marketing',25],
        ['Revenue','Profit',15], ['Operations','Payroll',40], ['Operations','Infrastructure',20]
      ]);
      const png = JupyterExcelCharts.render(graph);
      const img = document.createElement('img'); img.src = 'data:image/png;base64,' + png;
      img.style.width = '1000px'; document.body.appendChild(img);
      return png;
    });
    fs.writeFileSync('sankey-preview.png', Buffer.from(result, 'base64'));
    await page.locator('img').evaluate(img => img.decode());
    const colored = await page.evaluate(() => {
      const canvas = document.createElement('canvas'); canvas.width = 1000; canvas.height = 440;
      const ctx = canvas.getContext('2d'); ctx.drawImage(document.querySelector('img'),0,0,1000,440);
      const pixels = ctx.getImageData(0,0,1000,440).data;
      let count = 0;
      for(let i=0;i<pixels.length;i+=4) if(pixels[i]<240 || pixels[i+1]<240 || pixels[i+2]<240) count++;
      return count;
    });
    if(colored < 10000) throw Error('Blank or insufficiently rendered diagram');
    await page.screenshot({path:'sankey-browser.png'});
    console.log('Browser rendering passed; nonwhite pixels:', colored);
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode=1;});
