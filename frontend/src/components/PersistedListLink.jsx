import { Link } from 'react-router-dom'
import { listHref } from '../utils/listFilters'

/** Lien vers une liste en conservant les filtres mémorisés. */
export default function PersistedListLink({ pathname, storageKey, children, className, title }) {
  return (
    <Link to={listHref(pathname, storageKey)} className={className} title={title}>
      {children}
    </Link>
  )
}
