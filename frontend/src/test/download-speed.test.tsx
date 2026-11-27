import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DownloadSpeed } from '@/components/download-speed'

describe('overall download speed', () => {
  it('updates the combined transfer rate and resets to zero when the batch stops', () => {
    const { rerender } = render(<DownloadSpeed running bytesPerSecond={1024 * 1024 * 2.5} />)
    expect(screen.getByLabelText('Overall download speed')).toHaveTextContent('2.5 MB/s')
    rerender(<DownloadSpeed running bytesPerSecond={1024 * 800} />)
    expect(screen.getByLabelText('Overall download speed')).toHaveTextContent('800 KB/s')
    rerender(<DownloadSpeed running={false} bytesPerSecond={1024 * 1024} />)
    expect(screen.getByLabelText('Overall download speed')).toHaveTextContent('0 B/s')
  })
  it.each([0, 0.1, -1, NaN, Infinity])(
    'shows zero for a missing or invalid live rate %s',
    (value) => {
      render(<DownloadSpeed running bytesPerSecond={value} />)
      expect(screen.getByLabelText('Overall download speed')).toHaveTextContent('0 B/s')
    },
  )
})
