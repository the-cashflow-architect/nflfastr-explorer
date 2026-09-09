import { createContext } from 'react'

export type CrumbLabels = Record<string, string>

export const BreadcrumbLabelContext = createContext<{
  setLabel: (path: string, label: string) => void
  labels: CrumbLabels
}>({ setLabel: () => {}, labels: {} })
