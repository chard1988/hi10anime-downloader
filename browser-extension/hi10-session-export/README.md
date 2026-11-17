# Export an existing Hi10 Chrome session

This local Chrome/Edge extension exports the session from the browser profile you
already use. It does not start Playwright, ask for a password, submit a login form,
copy saved passwords or bypass CAPTCHA. No downloads from another software vendor
are required. Review the source before granting it access to your Hi10 cookies.

1. Stay signed in to Hi10 in your normal Chrome profile.
2. Open `chrome://extensions`, enable **Developer mode**, click **Load unpacked**,
   and select this `browser-extension/hi10-session-export` folder.
3. Open **Hi10 Session Export** from Chrome’s puzzle-piece Extensions menu.
4. Click **Save session.json**. Check Chrome’s Downloads for the saved file.
5. In the downloader WebUI, choose **Account & session → Choose session JSON** and
   select that file. The server verifies access after import.

Use `edge://extensions` for Edge. If your login is in a different Chrome profile,
load the extension in that profile. Incognito has a separate cookie store; use a
normal signed-in window. Browser policy can prevent loading unpacked extensions.

The extension requests `cookies` permission for **https://hi10anime.com only**.
This allows it to read authentication cookies, including HttpOnly cookies, on that
site. It reads them only when you click Save, filters to the exact site domain,
and writes Playwright-format JSON with no local-storage origins. It has no
background worker, content scripts, analytics, network calls or remote code. Its
extension-page policy disables network connections. Cookie editing/deletion and
Chrome saved-password access are not implemented.

Treat the exported file like a password. Do not send it in chat, commit it, or put
it in shared storage. Remove the extension after use if you do not need it again.
Copying cookies does not guarantee server acceptance: a session can expire or be
bound to a browser/IP. This tool preserves your existing cookies, without relaxing
site protections. The Docker image does not need rebuilding to import this file.

Chrome references: [cookies API](https://developer.chrome.com/docs/extensions/reference/api/cookies)
and [loading a local extension](https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world#load-unpacked).
