## Installing

Download the file for your computer, then:

**Windows** — run `MediaDownloader-windows-x64-setup.exe`. Windows may show a blue
"Windows protected your PC" box the first time: click **More info**, then **Run anyway**. The
installer puts *Media Downloader* in your Start menu (and on the desktop if you tick the box) and
can open it straight away. No admin password needed.

**macOS** — unzip `MediaDownloader-macos-x64.zip` and open `Media Downloader`. macOS will say it
"could not verify" the app (it isn't notarized by Apple): click **Done**, then open
**System Settings → Privacy & Security**, scroll to the bottom and click **Open Anyway** next to
*Media Downloader was blocked*, then open the app once more. That happens only the first time.
(Or, in Terminal, `xattr -cr "Media Downloader.app"` skips the dialogs.) The first launch can
take 20–30 seconds while macOS checks the new files.

**Linux** — `tar xzf MediaDownloader-linux-x64.tar.gz`, then run `MediaDownloader/MediaDownloader`.

The app opens in your web browser. Downloads go to `Downloads/Media Downloader` (change it in
Settings). Use the **Quit** button to stop it. If YouTube stops working one day, open Settings
and press **Update now** — the app also checks for downloader updates every time it starts.
