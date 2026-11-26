import { useState } from 'react'
import { Loader2, LockKeyhole } from 'lucide-react'
import type { Application } from '@/hooks/use-application'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { ThemeSwitcher } from '@/components/theme-switcher'
export function LoginForm({ app }: { app: Application }) {
  const [password, setPassword] = useState('')
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-6 bg-muted/30 p-6">
      <div className="flex w-full max-w-md items-center justify-between">
        <a href="/" className="flex items-center gap-2 font-semibold">
          <span className="rounded-lg bg-primary p-2 text-primary-foreground">
            <LockKeyhole className="size-5" />
          </span>
          Hi10
        </a>
        <ThemeSwitcher />
      </div>
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">Your library awaits.</CardTitle>
          <CardDescription>Unlock your private download manager.</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={async (e) => {
              e.preventDefault()
              if (await app.action('/api/unlock', { password }, 'Library unlocked')) setPassword('')
            }}
          >
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="web-password">Web interface password</FieldLabel>
                <Input
                  id="web-password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <FieldDescription>
                  This is your app password, separate from your Hi10 account. A generated password
                  is stored in appdata’s web-password.json.
                </FieldDescription>
              </Field>
              <Field>
                <Button type="submit" disabled={!!app.pending}>
                  {app.pending ? <Loader2 className="animate-spin" /> : <LockKeyhole />}Unlock
                  library
                </Button>
              </Field>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
      <p className="max-w-sm text-center text-xs text-muted-foreground">
        Your session and downloads stay on your server.
      </p>
    </div>
  )
}
