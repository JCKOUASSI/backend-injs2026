import { LIST_STORAGE_KEYS } from '../utils/listFilters'
import PersistedListLink from './PersistedListLink'

/** Lien vers la liste des modules en conservant les filtres actifs. */
export default function ModulesListLink({ children, className, title }) {
  return (
    <PersistedListLink
      pathname="/modules"
      storageKey={LIST_STORAGE_KEYS.modules}
      className={className}
      title={title}
    >
      {children}
    </PersistedListLink>
  )
}
