import { Fragment, useState, type ReactNode } from 'react'
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
  type SortingState,
} from '@tanstack/react-table'
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { SearchCombobox } from '@/components/search-combobox'
import { IconButton } from '@/components/icon-button'
import { Skeleton } from '@/components/ui/skeleton'

export function DataTable<T extends { id: string }>({
  data,
  columns,
  selection,
  onSelectionChange,
  renderExpanded,
  manual,
  loading = false,
  empty = 'No matching items',
}: {
  data: T[]
  columns: ColumnDef<T>[]
  selection?: RowSelectionState
  onSelectionChange?: (value: RowSelectionState) => void
  renderExpanded?: (row: T) => ReactNode
  manual?: {
    page: number
    size: number
    pages: number
    total: number
    onPage: (page: number) => void
    onSize: (size: number) => void
  }
  loading?: boolean
  empty?: string
}) {
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 25 }),
    [sorting, setSorting] = useState<SortingState>([])
  const table = useReactTable({
    data,
    columns,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    state: {
      pagination: manual ? { pageIndex: manual.page, pageSize: manual.size } : pagination,
      sorting,
      rowSelection: selection || {},
    },
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    manualPagination: !!manual,
    pageCount: manual?.pages,
    onRowSelectionChange: (updater) => {
      if (onSelectionChange)
        onSelectionChange(typeof updater === 'function' ? updater(selection || {}) : updater)
    },
  })
  const page = manual?.page ?? table.getState().pagination.pageIndex,
    size = manual?.size ?? table.getState().pagination.pageSize,
    pages = manual?.pages ?? Math.max(1, table.getPageCount())
  const total = manual?.total ?? data.length
  const go = (value: number) => (manual ? manual.onPage(value) : table.setPageIndex(value))
  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-lg border bg-card">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((group) => (
              <TableRow key={group.id}>
                {group.headers.map((header) => (
                  <TableHead key={header.id}>
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {loading ? (
              Array.from({ length: 5 }, (_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={columns.length}>
                    <Skeleton className="h-9 w-full" />
                  </TableCell>
                </TableRow>
              ))
            ) : table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <Fragment key={row.id}>
                  <TableRow data-state={row.getIsSelected() ? 'selected' : undefined}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </TableCell>
                    ))}
                  </TableRow>
                  {renderExpanded?.(row.original)}
                </Fragment>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-36 text-center text-muted-foreground"
                >
                  {empty}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4 text-sm text-muted-foreground">
        <span>
          {total ? page * size + 1 : 0}–{Math.min((page + 1) * size, total)} of {total} items
        </span>
        <div className="flex flex-wrap items-center gap-4">
          <SearchCombobox
            label="Rows per page"
            value={String(size)}
            onChange={(value) => {
              manual ? manual.onSize(Number(value)) : table.setPageSize(Number(value))
            }}
            options={[5, 10, 25, 50, 100].map((n) => ({ value: String(n), label: `${n} rows` }))}
            className="w-28"
          />
          <span>
            Page {Math.min(page + 1, pages)} of {Math.max(1, pages)}
          </span>
          <div className="flex">
            <IconButton label="First page" disabled={page === 0} onClick={() => go(0)}>
              <ChevronsLeft />
            </IconButton>
            <IconButton label="Previous page" disabled={page === 0} onClick={() => go(page - 1)}>
              <ChevronLeft />
            </IconButton>
            <IconButton label="Next page" disabled={page + 1 >= pages} onClick={() => go(page + 1)}>
              <ChevronRight />
            </IconButton>
            <IconButton
              label="Last page"
              disabled={page + 1 >= pages}
              onClick={() => go(pages - 1)}
            >
              <ChevronsRight />
            </IconButton>
          </div>
        </div>
      </div>
    </div>
  )
}
