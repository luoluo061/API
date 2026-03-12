const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

async function main() {
  const outputDir = path.resolve('output', 'playwright');
  fs.mkdirSync(outputDir, { recursive: true });

  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true,
  });

  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
  const prompt = '请只回复 OK，不要添加任何解释。';

  try {
    await page.goto('https://www.doubao.com/chat/', {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
    await page.waitForTimeout(4000);

    const input = page.locator("textarea, div[contenteditable='true']").first();
    await input.waitFor({ timeout: 15000 });
    await input.click();

    const tagName = await input.evaluate((node) => node.tagName.toLowerCase());
    if (tagName === 'textarea') {
      await input.fill(prompt);
    } else {
      await input.fill('');
      await input.type(prompt);
    }

    const sendButton = page.locator("button[type='submit']").last();
    await sendButton.waitFor({ timeout: 10000 });
    await sendButton.click();

    await page.waitForTimeout(3000);
    const responseLocator = page.locator("[data-testid='message-content'], .message-content, .answer-content").last();
    await responseLocator.waitFor({ timeout: 90000 });
    await page.waitForTimeout(5000);

    const responseText = (await responseLocator.innerText()).trim();
    const result = {
      url: page.url(),
      title: await page.title(),
      prompt,
      responseText,
      loginButtonCount: await page.locator("text=登录").count(),
      textareaCount: await page.locator("textarea, div[contenteditable='true']").count(),
      timestamp: new Date().toISOString(),
    };

    await page.screenshot({
      path: path.join(outputDir, 'doubao-call-result.png'),
      fullPage: true,
    });
    fs.writeFileSync(
      path.join(outputDir, 'doubao-call-result.json'),
      JSON.stringify(result, null, 2),
      'utf8'
    );
    console.log(JSON.stringify(result, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
