import { useEffect, useRef, useState } from 'react'
import {
  CheckCircle2,
  ExternalLink,
  Loader2,
  RefreshCw,
  Save,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import type { Application } from '@/hooks/use-application'
import { api, errorText } from '@/lib/api'
import { FormSheet } from '@/components/form-sheet'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { toast } from '@/components/ui/toast'

export function SessionPage({ app, active }: { app: Application; active: boolean }) {
  const session = app.state!.session,
    [importOpen, setImportOpen] = useState(false),
    [credentialsOpen, setCredentialsOpen] = useState(false),
    [removeOpen, setRemoveOpen] = useState(false)
  const [username, setUsername] = useState(''),
    [password, setPassword] = useState(''),
    [image, setImage] = useState(''),
    [text, setText] = useState(''),
    [inputBusy, setInputBusy] = useState(false)
  const screenshotRef = useRef<(() => Promise<void>) | null>(null)
  const imageUrl = useRef(''),
    inputChain = useRef<Promise<unknown>>(Promise.resolve()),
    browser = app.state!.browser_active
  useEffect(() => {
    if (!browser || !active) {
      setImage('')
      return
    }
    let live = true,
      working = false
    const controller = new AbortController()
    async function screenshot() {
      if (working || document.hidden) return
      working = true
      try {
        const response = await fetch('/api/browser/image', { signal: controller.signal })
        if (!response.ok) return
        const blob = await response.blob()
        if (!live) return
        const next = URL.createObjectURL(blob)
        if (imageUrl.current) URL.revokeObjectURL(imageUrl.current)
        imageUrl.current = next
        setImage(next)
      } catch {
        /* Poll again while the browser is running. */
      } finally {
        working = false
      }
    }
    screenshotRef.current = screenshot
    void screenshot()
    const timer = setInterval(screenshot, 2500)
    return () => {
      live = false
      controller.abort()
      clearInterval(timer)
      if (imageUrl.current) URL.revokeObjectURL(imageUrl.current)
      imageUrl.current = ''
      screenshotRef.current = null
    }
  }, [browser, active])
  const input = (data: Record<string, unknown>) => {
    setInputBusy(true)
    inputChain.current = inputChain.current
      .then(async () => {
        await api('/api/browser/action', data)
        await screenshotRef.current?.()
      })
      .catch((error) =>
        toast.add({ title: 'Browser input failed', description: errorText(error), type: 'error' }),
      )
      .finally(() => setInputBusy(false))
    return inputChain.current
  }
  const busy = app.busy || !!app.pending
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-medium tracking-widest text-muted-foreground uppercase">
          Connect once. Keep exploring.
        </p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Account & session</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Use your existing browser session or sign in and save it on your server.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {session.status === 'checking' ? (
              <Loader2 className="size-5 animate-spin" />
            ) : (
              <CheckCircle2 className="size-5" />
            )}
            {session.connected
              ? 'Session connected'
              : session.saved
                ? 'Saved session needs verification'
                : 'No session saved'}
          </CardTitle>
          <CardDescription>{session.message}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={busy || !session.saved}
            onClick={() => app.action('/api/session/verify', {}, 'Session verification requested')}
          >
            <RefreshCw />
            Verify session
          </Button>
          <Button
            variant="destructive"
            disabled={busy || !session.saved}
            onClick={() => setRemoveOpen(true)}
          >
            <Trash2 />
            Remove saved session
          </Button>
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <Badge variant="outline" className="w-fit">
              Recommended
            </Badge>
            <CardTitle>Already signed in?</CardTitle>
            <CardDescription>
              Import your Playwright session JSON from the Hi10 browser exporter or desktop login
              helper.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => setImportOpen(true)} disabled={busy}>
              <Upload />
              Import session
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <Badge variant="outline" className="w-fit">
              Alternative
            </Badge>
            <CardTitle>Use the login browser</CardTitle>
            <CardDescription>
              Complete the real website login and CAPTCHA, then save your session. Hardened hosts
              may require session import.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => app.action('/api/browser/start', {}, 'Opening login browser')}
            >
              <ExternalLink />
              Open login browser
            </Button>
          </CardContent>
        </Card>
      </div>
      {browser && (
        <Card>
          <CardHeader>
            <CardTitle>Hi10 login browser</CardTitle>
            <CardDescription>
              Click the image and type. Use the website’s Log In button after CAPTCHA loads.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => setCredentialsOpen(true)}>
                Fill login fields
              </Button>
              <Button
                disabled={busy}
                onClick={() =>
                  app.action('/api/browser/capture', {}, 'Checking and saving session')
                }
              >
                <Save />
                Save session
              </Button>
              <Button
                variant="outline"
                disabled={inputBusy}
                onClick={async () => {
                  await input({ action: 'close' })
                  await app.refresh()
                }}
              >
                <X />
                Close browser
              </Button>
            </div>
            {image ? (
              <img
                src={image}
                alt="Live Hi10 login browser"
                tabIndex={0}
                className="w-full max-w-5xl rounded-lg border outline-offset-4"
                draggable={false}
                onClick={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect()
                  e.currentTarget.focus()
                  void input({
                    action: 'click',
                    x: ((e.clientX - rect.left) * 1000) / rect.width,
                    y: ((e.clientY - rect.top) * 760) / rect.height,
                  })
                }}
                onKeyDown={(e) => {
                  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
                    e.preventDefault()
                    void input({ action: 'key', key: 'Control+A' })
                  } else if (
                    [
                      'Tab',
                      'Enter',
                      'Backspace',
                      'Delete',
                      'ArrowLeft',
                      'ArrowRight',
                      'ArrowUp',
                      'ArrowDown',
                      'Escape',
                    ].includes(e.key)
                  ) {
                    e.preventDefault()
                    void input({ action: 'key', key: e.key })
                  } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
                    e.preventDefault()
                    void input({ action: 'text', text: e.key })
                  }
                }}
                onPaste={(e) => {
                  e.preventDefault()
                  void input({ action: 'text', text: e.clipboardData.getData('text') })
                }}
                onWheel={(e) => void input({ action: 'scroll', delta: e.deltaY })}
              />
            ) : (
              <Loader2 className="animate-spin" aria-label="Opening browser" />
            )}
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                void input({ action: 'text', text })
                setText('')
              }}
            >
              <Input
                type="password"
                aria-label="Text for focused browser field"
                placeholder="Send text to the focused field"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <Button variant="outline" type="submit" disabled={inputBusy}>
                Send text
              </Button>
              <Button
                variant="outline"
                type="button"
                onClick={() => input({ action: 'key', key: 'Enter' })}
              >
                Enter
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
      <FormSheet
        open={importOpen}
        onOpenChange={setImportOpen}
        title="Import a session"
        description="Select a Playwright session JSON. The app verifies access before marking the session connected."
      >
        <div className="space-y-4">
          <Label htmlFor="session-file">Session JSON</Label>
          <Input
            id="session-file"
            type="file"
            accept="application/json,.json"
            disabled={busy}
            onChange={async (e) => {
              const file = e.target.files?.[0]
              if (!file) return
              try {
                if (file.size > 2 * 1024 * 1024) throw new Error('Session file exceeds 2 MB')
                const state = JSON.parse(await file.text())
                if (
                  await app.action(
                    '/api/session/import',
                    { state },
                    'Session imported; verifying access',
                  )
                )
                  setImportOpen(false)
              } catch (error) {
                toast.add({ title: 'Import failed', description: errorText(error), type: 'error' })
              } finally {
                e.target.value = ''
              }
            }}
          />
          <p className="text-sm text-muted-foreground">
            Your session contains authentication cookies. Sessions can expire or be tied to an IP
            address.
          </p>
        </div>
      </FormSheet>
      <FormSheet
        open={credentialsOpen}
        onOpenChange={(value) => {
          setCredentialsOpen(value)
          if (!value) setPassword('')
        }}
        title="Fill login fields"
        description="This fills the fields only. Complete CAPTCHA and click Log In inside the website."
      >
        <form
          className="space-y-4"
          onSubmit={async (e) => {
            e.preventDefault()
            const value = password
            setPassword('')
            await input({ action: 'credentials', username, password: value })
            setCredentialsOpen(false)
          }}
        >
          <Label htmlFor="hi10-username">Hi10 username or email</Label>
          <Input
            id="hi10-username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <Label htmlFor="hi10-password">Hi10 password</Label>
          <Input
            id="hi10-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <Button type="submit" disabled={inputBusy}>
            Fill fields
          </Button>
        </form>
      </FormSheet>
      <FormSheet
        open={removeOpen}
        onOpenChange={setRemoveOpen}
        title="Remove saved session"
        description="Remove the saved Hi10 authentication session from this server. Your library, queue and downloaded files are retained."
      >
        <Button
          variant="destructive"
          disabled={busy}
          onClick={async () => {
            if (await app.action('/api/session/delete', {}, 'Saved session removed'))
              setRemoveOpen(false)
          }}
        >
          <Trash2 />
          Remove session
        </Button>
      </FormSheet>
    </div>
  )
}
