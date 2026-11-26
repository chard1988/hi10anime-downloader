import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DataTable } from '@/components/data-table'
import { SearchCombobox } from '@/components/search-combobox'
import { TooltipProvider } from '@/components/ui/tooltip'
const data = Array.from({ length: 70 }, (_, i) => ({ id: String(i), title: `Project ${i}` }))
describe('shadcn data table', () => {
  it('bounds rows and navigates without discarding other data', async () => {
    const user = userEvent.setup()
    render(
      <TooltipProvider>
        <DataTable data={data} columns={[{ accessorKey: 'title', header: 'Project' }]} />
      </TooltipProvider>,
    )
    expect(screen.getAllByRole('row')).toHaveLength(26)
    expect(screen.getByText('Project 0')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Next page' }))
    expect(screen.getByText('Project 25')).toBeInTheDocument()
    expect(screen.queryByText('Project 0')).not.toBeInTheDocument()
  })
  it('searches combobox options before selecting a value', async () => {
    const user = userEvent.setup(),
      change = vi.fn()
    render(
      <SearchCombobox
        label="Filter"
        value="all"
        onChange={change}
        options={[
          { value: 'all', label: 'All projects' },
          { value: 'failed', label: 'Failed projects' },
        ]}
      />,
    )
    const input = screen.getByRole('combobox', { name: 'Filter' })
    await user.click(input)
    await user.clear(input)
    await user.type(input, 'Failed')
    await user.click(await screen.findByRole('option', { name: 'Failed projects' }))
    expect(change).toHaveBeenCalledWith('failed')
  })
})
