import { useContext, useEffect } from 'react'
import { BreadcrumbLabelContext } from './breadcrumbContext'

/**
 * A page calls this once its payload arrives, replacing the label the
 * breadcrumb derived from the URL with the entity's real name.
 */
export function useCrumbLabel(path: string | null, label: string | null | undefined): void {
  const { setLabel } = useContext(BreadcrumbLabelContext)
  useEffect(() => {
    if (path && label) setLabel(path, label)
  }, [path, label, setLabel])
}
