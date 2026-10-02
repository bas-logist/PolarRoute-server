import { describe, expect, it } from 'vitest'
import { isActiveStatus, isTerminalStatus, statusTone } from './status'

describe('status helpers', () => {
  it('identifies terminal and active states', () => {
    expect(['SUCCESS', 'FAILURE', 'REVOKED'].every(isTerminalStatus)).toBe(true)
    expect(['PENDING', 'STARTED', 'RETRY'].some(isTerminalStatus)).toBe(false)
    expect(isActiveStatus('STARTED')).toBe(true)
    expect(isActiveStatus('SUCCESS')).toBe(false)
  })

  it('maps statuses to Style Kit contextual tones', () => {
    expect(statusTone('SUCCESS')).toBe('success')
    expect(statusTone('PENDING')).toBe('info')
    expect(statusTone('STARTED')).toBe('info')
    expect(statusTone('FAILURE')).toBe('danger')
    expect(statusTone('REVOKED')).toBe('danger')
    expect(statusTone('UNKNOWN')).toBe('default')
  })
})
