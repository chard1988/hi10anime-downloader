import type { ReactNode } from 'react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
export function FormSheet({
  open,
  onOpenChange,
  title,
  description,
  children,
  wide = false,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  children: ReactNode
  wide?: boolean
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className={wide ? 'w-full sm:max-w-3xl' : 'w-full sm:max-w-lg'}>
        <SheetHeader className="pr-14">
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>{description}</SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-6 pb-8">{children}</div>
      </SheetContent>
    </Sheet>
  )
}
