import { useMemo } from 'react'
import {
  Combobox,
  ComboboxInput,
  ComboboxContent,
  ComboboxList,
  ComboboxItem,
  ComboboxEmpty,
} from '@/components/ui/combobox'
export type Option = { value: string; label: string }
export function SearchCombobox({
  value,
  onChange,
  options,
  label,
  disabled = false,
  className = 'w-44',
}: {
  value: string
  onChange: (value: string) => void
  options: Option[]
  label: string
  disabled?: boolean
  className?: string
}) {
  // Base UI observes item/value identity. Keep equal option sets stable across polls.
  const serialized = JSON.stringify(options)
  const items = useMemo<Option[]>(() => JSON.parse(serialized), [serialized])
  const selected = items.find((o) => o.value === value) ?? null
  return (
    <Combobox
      items={items}
      value={selected}
      onValueChange={(option) => {
        if (option) onChange(option.value)
      }}
      itemToStringLabel={(o) => o.label}
      isItemEqualToValue={(a, b) => a.value === b.value}
      disabled={disabled}
    >
      <ComboboxInput
        aria-label={label}
        placeholder={label}
        className={className}
        disabled={disabled}
      />
      <ComboboxContent>
        <ComboboxEmpty>No matching options</ComboboxEmpty>
        <ComboboxList>
          {(option: Option) => (
            <ComboboxItem key={option.value} value={option}>
              {option.label}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  )
}
