import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'
import ConfirmModal from '../components/ConfirmModal'
import { useToast } from '../context/ToastContext'
import { useDebounce } from '../hooks/useDebounce'
import { useAuth } from '../context/AuthContext'
import {
  buildUsersSearchParams,
  LIST_STORAGE_KEYS,
  parseListPage,
  readUsersFilters,
} from '../utils/listFilters'
import { usePersistedListQuery } from '../hooks/usePersistedListQuery'
import Pagination from '../components/Pagination'
import { parsePaginatedResponse } from '../utils/paginatedResponse'
import { formatApiErrors } from '../utils/apiErrors'
import { useSecretariats } from '../hooks/useSecretariats'
import { useQueryClient } from '@tanstack/react-query'
import { SECRETARIATS_QUERY_KEY } from '../lib/queryClient'
import '../styles/profils.css'
import '../pages/habilitations/habilitations.css'
import NavigationUtilisateursAcces from './habilitations/NavigationUtilisateursAcces'

const TAB_CONFIG = {
  personnel: { title: 'Liste des utilisateurs', description: 'Comptes du personnel administratif, technique et pédagogique.', icon: 'bi-person-gear', createLabel: 'Nouvel utilisateur', modalTitle: 'Nouvel utilisateur' },
  auditeurs: { title: 'Comptes étudiants', description: 'Comptes étudiants (auditeurs) inscrits aux formations.', icon: 'bi-person-badge', createLabel: 'Nouveau compte étudiant', modalTitle: 'Nouveau compte étudiant' },
  formateurs: { title: 'Comptes enseignants', description: 'Comptes enseignants et intervenants pédagogiques.', icon: 'bi-person-video3', createLabel: 'Nouveau compte enseignant', modalTitle: 'Nouveau compte enseignant' },
}
const emptyForm = { username: '', first_name: '', last_name: '', email: '', matricule: '', role: 'ENCADRANT', password: '', telephone: '', secretariat: '', new_secretariat_nom: '', new_secretariat_type: '' }
const emptyEditForm = { username: '', first_name: '', last_name: '', email: '', matricule: '', role: '', telephone: '', is_active: true, password: '', secretariat: '' }

export default function Users() {
  const { user: currentUser } = useAuth()
  const roleContext = currentUser?.role_context || {}
  const roleLabels = roleContext.labels || {}
  const roleLabel = (role) => String(roleLabels[role] || role).replaceAll('CPFAE', 'INJS')
  const badgeAccountRoles = roleContext.badge_account_roles || ['AUDITEUR', 'FORMATEUR']
  const canManageUsers = Boolean(roleContext.can_mutate_users)
  const creatableRoles = canManageUsers ? (roleContext.manageable_roles || []) : []
  const staffRoleOptions = creatableRoles.filter(r => !badgeAccountRoles.includes(r))
  const staffFilterRoles = roleContext.staff_filter_roles?.length
    ? roleContext.staff_filter_roles
    : staffRoleOptions
  const canManageAuditeurAccounts = canManageUsers && creatableRoles.includes('AUDITEUR')
  const canManageFormateurAccounts = canManageUsers && creatableRoles.includes('FORMATEUR')
  const showStaffSection = canManageUsers
    ? staffRoleOptions.length > 0
    : staffFilterRoles.length > 0
  const showAuditeursSection = canManageAuditeurAccounts
  const showFormateursSection = canManageFormateurAccounts
  const availableTabs = [
    showStaffSection && { id: 'personnel', label: 'Utilisateurs', icon: 'bi-person-gear' },
    showAuditeursSection && { id: 'auditeurs', label: 'Comptes étudiants', icon: 'bi-person-badge' },
    showFormateursSection && { id: 'formateurs', label: 'Comptes enseignants', icon: 'bi-person-video3' },
  ].filter(Boolean)
  const showTabBar = availableTabs.length > 1
  const [searchParams] = useSearchParams()
  const initialUsers = readUsersFilters(searchParams)
  const [userTab, setUserTab] = useState(initialUsers.tab)
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [page, setPage] = useState(() => parseListPage(searchParams))
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [search, setSearch] = useState(initialUsers.search)
  const [roleFilter, setRoleFilter] = useState(initialUsers.role)
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ ...emptyForm })
  const [formError, setFormError] = useState('')

  const [showEditModal, setShowEditModal] = useState(false)
  const [editingUser, setEditingUser] = useState(null)
  const [editForm, setEditForm] = useState({ ...emptyEditForm })
  const [editError, setEditError] = useState('')
  const [saving, setSaving] = useState(false)
  const queryClient = useQueryClient()
  const { data: secretariats = [] } = useSecretariats()
  const [confirmDialog, setConfirmDialog] = useState(null)
  const { showToast } = useToast()

  const debouncedSearch = useDebounce(search)
  // Faux positif exhaustive-deps (tranché au LOT 6, cf. TESTS_FRONTEND §10.2) :
  // le repli d'onglet ne dépend que des trois DISPONIBILITÉS dérivées des
  // permissions. `availableTabs` est un tableau neuf à chaque rendu : l'ajouter
  // ferait boucler l'effet (setUserTab → rendu → effet…). `userTab` est lu dans
  // sa version courante au moment où une disponibilité change, sans désuétude.
  // Régressions : Users.test.jsx « replie sur un onglet disponible ».
  useEffect(() => {
    if (!availableTabs.some(t => t.id === userTab)) {
      setUserTab(availableTabs[0]?.id || 'personnel')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showStaffSection, showAuditeursSection, showFormateursSection])

  usePersistedListQuery(
    LIST_STORAGE_KEYS.users,
    () => buildUsersSearchParams(userTab, roleFilter, page, debouncedSearch),
    [userTab, roleFilter, page, debouncedSearch],
  )

  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  useEffect(() => { loadUsers() }, [page, debouncedSearch, roleFilter, userTab])

  const setUserTabAndReset = (tab) => {
    setUserTab(tab)
    setPage(1)
    if (tab !== 'personnel') setRoleFilter('')
  }

  const loadUsers = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page })
      if (debouncedSearch) params.set('search', debouncedSearch)
      if (userTab === 'personnel') {
        params.set('exclude_role', badgeAccountRoles.join(','))
        if (roleFilter) params.set('role', roleFilter)
      } else if (userTab === 'auditeurs') {
        params.set('role', 'AUDITEUR')
      } else if (userTab === 'formateurs') {
        params.set('role', 'FORMATEUR')
      }
      const response = await api.get(`/auth/users/?${params}`)
      const pageSize = 50
      const { results, count, totalPages: pages } = parsePaginatedResponse(response.data, pageSize)
      setUsers(results)
      setTotalCount(count)
      setTotalPages(pages)
    } catch (err) {
      console.error('Chargement utilisateurs:', err)
      setError(formatApiErrors(err.response?.data, { fallback: 'Erreur lors du chargement des utilisateurs.' }))
    } finally { setLoading(false) }
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    setFormError('')
    setSaving(true)
    try {
      const { new_secretariat_nom, new_secretariat_type, ...userPayload } = form
      if (!userPayload.secretariat) delete userPayload.secretariat
      const res = await api.post('/auth/users/', userPayload)
      const newUser = res.data
      if (form.role === 'SECRETARIAT' && !form.secretariat && new_secretariat_nom) {
        const secRes = await api.post('/formations/secretariats/', {
          nom: new_secretariat_nom,
          type: new_secretariat_type || '',
          responsable: newUser.id,
        })
        await api.patch(`/auth/users/${newUser.id}/`, { secretariat: secRes.data.id })
        queryClient.setQueryData(SECRETARIATS_QUERY_KEY, (old) => [...(old || []), secRes.data])
      }
      setShowModal(false)
      setForm({ ...emptyForm })
      loadUsers()
      showToast(
        form.role === 'AUDITEUR' ? 'Compte étudiant créé'
          : form.role === 'FORMATEUR' ? 'Compte enseignant créé'
          : 'Utilisateur créé'
      )
    } catch (err) {
      console.error('Création utilisateur:', err)
      setFormError(formatApiErrors(err.response?.data, { fallback: 'Erreur lors de la création de l\'utilisateur.' }))
    } finally { setSaving(false) }
  }

  const handleDelete = (id) => {
    setConfirmDialog({
      message: 'Supprimer cet utilisateur ?',
      detail: 'Cette action est définitive.',
      onConfirm: async () => {
        try {
          await api.delete(`/auth/users/${id}/`)
          loadUsers()
          showToast('Utilisateur supprimé')
        } catch (err) {
          console.error('Suppression utilisateur:', err)
          // §10.14 (corrigé au LOT 37) : le toast d'erreur applique le même
          // rebranding CPFAE -> INJS que les badges et les alertes des modales.
          showToast(String(formatApiErrors(err.response?.data, { fallback: 'Erreur lors de la suppression.' })).replaceAll('CPFAE', 'INJS'), 'error')
        }
      }
    })
  }

  const openEdit = (u) => {
    setEditingUser(u)
    setEditForm({
      username: u.username || '',
      first_name: u.first_name || '',
      last_name: u.last_name || '',
      email: u.email || '',
      matricule: u.matricule || '',
      role: u.role || '',
      telephone: u.telephone || '',
      is_active: u.is_active !== false,
      password: '',
      secretariat: u.secretariat || '',
    })
    setEditError('')
    setShowEditModal(true)
  }

  const handleEdit = async (e) => {
    e.preventDefault()
    setEditError('')
    setSaving(true)
    try {
      const payload = { ...editForm }
      if (!payload.password) delete payload.password
      if (!payload.secretariat) payload.secretariat = null
      await api.patch(`/auth/users/${editingUser.id}/`, payload)
      setShowEditModal(false)
      loadUsers()
      showToast('Utilisateur modifié')
    } catch (err) {
      console.error('Modification utilisateur:', err)
      setEditError(formatApiErrors(err.response?.data, { fallback: 'Erreur lors de la modification de l\'utilisateur.' }))
    } finally { setSaving(false) }
  }

  const getRoleBadge = (role) => ({ 'DIRECTION': 'badge-direction', 'CHEF_INJS_ADMIN': 'badge-dfrc', 'INJS_ADMIN': 'badge-dfrc', 'CHEF_SECRETARIAT': 'badge-secretariat', 'SECRETARIAT': 'badge-secretariat', 'FINANCE': 'badge-info', 'ARCHIVE': 'badge-info', 'ENCADRANT': 'badge-encadrant', 'FORMATEUR': 'badge-formateur', 'AUDITEUR': 'badge-auditeur' }[role] || 'badge-info')

  const getFullName = (u) => `${u.first_name || ''} ${u.last_name || ''}`.trim() || u.username
  const getInitials = (u) => `${(u.first_name || '')[0] || ''}${(u.last_name || '')[0] || ''}`.toUpperCase() || u.username[0]?.toUpperCase()

  const tabMeta = TAB_CONFIG[userTab] || TAB_CONFIG.personnel
  const listTitle = tabMeta.title
  const listIcon = tabMeta.icon
  const canCreateOnTab = canManageUsers && (userTab === 'personnel'
    ? staffRoleOptions.length > 0
    : userTab === 'auditeurs'
      ? canManageAuditeurAccounts
      : canManageFormateurAccounts)
  const createRoleForTab = userTab === 'auditeurs' ? 'AUDITEUR' : userTab === 'formateurs' ? 'FORMATEUR' : staffRoleOptions[0]
  const matriculeLabel = userTab === 'formateurs'
    ? 'N° badge enseignant'
    : 'N° Matricule (badge)'

  return (
    <div className="container-fluid py-3">
      <div className="prof-bandeau" role="note">
        <i className="bi bi-journal-lock" aria-hidden="true"></i>
        <span>Toute action sur les comptes est tracée dans le journal des accès, immuable et horodaté.</span>
      </div>
      <h2 className="prof-entete">
        <i className="bi bi-shield-lock" aria-hidden="true"></i>
        <span>Gestion des profils — Utilisateurs & Accès</span>
      </h2>
      <p className="prof-sous-titre">Répertoire des comptes du personnel, des comptes étudiants et des comptes enseignants de l'INJS.</p>
      <div className="hab-layout">
        <div className="d-flex flex-column gap-3">
          <NavigationUtilisateursAcces compact />
          {showTabBar && (
            <nav className="prof-nav" role="tablist" aria-label="Catégories de profils">
              {availableTabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={userTab === tab.id}
                  className={userTab === tab.id ? 'active' : ''}
                  onClick={() => setUserTabAndReset(tab.id)}
                >
                  <i className={`bi ${tab.icon}`} aria-hidden="true"></i>{tab.label}
                </button>
              ))}
            </nav>
          )}
        </div>
        <div className="prof-contenu">
          {/* Search + filter bar */}
          <div className="prof-carte">
            <div className="prof-filtres">
              <div className="prof-recherche input-group">
                <span className="input-group-text"><i className="bi bi-search"></i></span>
                <input type="text" className="form-control" placeholder="Rechercher par nom, username, matricule..."
                  value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
              </div>
              {userTab === 'personnel' && staffFilterRoles.length > 0 && (
                <div>
                  <select className="form-control" value={roleFilter} onChange={(e) => { setRoleFilter(e.target.value); setPage(1) }}>
                    <option value="">Tous les rôles</option>
                    {staffFilterRoles.map(r => <option key={r} value={r}>{roleLabel(r)}</option>)}
                  </select>
                </div>
              )}
              {canCreateOnTab && (
                <button type="button" onClick={() => { setForm({ ...emptyForm, role: createRoleForTab }); setFormError(''); setShowModal(true) }} className="btn btn-dfrc">
                  <i className="bi bi-plus-lg me-1"></i>{tabMeta.createLabel}
                </button>
              )}
            </div>
          </div>

          {error && <div className="error-message">{error}</div>}

          {/* Table */}
          <div className="prof-carte">
            <div className="prof-carte-entete">
              <div>
                <h3 className="prof-carte-titre"><i className={`bi ${listIcon} me-2`}></i>{listTitle}</h3>
                <p className="prof-carte-sous-titre">{tabMeta.description}</p>
              </div>
              <span className="prof-compteur">{users.length} résultat(s)</span>
            </div>
            <div className="prof-carte-corps">
          {loading ? <div className="loading"><div className="spinner"></div></div> : (
            <>
              <div className="prof-table-wrap">
                <table className="prof-table">
                  <thead>
                    <tr>
                      <th>Nom complet</th>
                      <th>Identifiant</th>
                      <th>N° matricule</th>
                      <th>Adresse e-mail</th>
                      <th>Rôle / Secrétariat</th>
                      <th>Téléphone</th>
                      <th>Actif</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.length > 0 ? users.map((u) => (
                      <tr key={u.id}>
                        <td>
                          <div className="prof-cellule-identite">
                            <div className="prof-avatar">{getInitials(u)}</div>
                            <strong>{getFullName(u)}</strong>
                          </div>
                        </td>
                        <td>{u.username}</td>
                        <td>{u.matricule || '-'}</td>
                        <td>{u.email || '-'}</td>
                        <td>
                          <span className={`badge ${getRoleBadge(u.role)}`}>{roleLabel(u.role)}</span>
                          {u.secretariat_nom && <><br/><small className="text-muted">{u.secretariat_nom}</small></>}
                        </td>
                        <td>{u.telephone || '-'}</td>
                        <td>
                          <span className={`badge ${u.is_active ? 'badge-success' : 'badge-danger'}`}>
                            {u.is_active ? 'Actif' : 'Inactif'}
                          </span>
                        </td>
                        <td>
                          <div className="btn-group">
                            {canManageUsers && creatableRoles.includes(u.role) && (
                              <button onClick={() => openEdit(u)} className="btn btn-outline-primary btn-sm" title="Modifier">
                                <i className="bi bi-pencil"></i>
                              </button>
                            )}
                            {canManageUsers && creatableRoles.includes(u.role) && (
                              <button onClick={() => handleDelete(u.id)} className="btn btn-outline-danger btn-sm" title="Supprimer">
                                <i className="bi bi-trash"></i>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )) : (
                      <tr><td colSpan="8" className="text-center py-4 text-muted">Aucun utilisateur trouvé</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                totalItems={totalCount}
                pageSize={50}
              />
            </>
          )}
            </div>
          </div>
        </div>
      </div>

      {confirmDialog && (
        <ConfirmModal
          message={confirmDialog.message}
          detail={confirmDialog.detail}
          onConfirm={() => { setConfirmDialog(null); confirmDialog.onConfirm() }}
          onCancel={() => setConfirmDialog(null)}
        />
      )}

      {/* Create User Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" style={{ maxHeight: 'calc(100vh - 3rem)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5>{tabMeta.modalTitle}</h5>
              <button className="btn-close" onClick={() => setShowModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <div className="modal-body" style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
                {formError && <div className="alert alert-danger" style={{ whiteSpace: 'pre-line', fontSize: '0.85rem', padding: '0.5rem 0.75rem' }}>{String(formError).replaceAll('CPFAE', 'INJS')}</div>}
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Prénom</label>
                    <input type="text" className="form-control" value={form.first_name} onChange={e => setForm({...form, first_name: e.target.value})} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Nom</label>
                    <input type="text" className="form-control" value={form.last_name} onChange={e => setForm({...form, last_name: e.target.value})} />
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Nom d'utilisateur *</label>
                    <input type="text" className="form-control" required value={form.username} onChange={e => setForm({...form, username: e.target.value})} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Rôle *</label>
                    <select className="form-control" required value={form.role} onChange={e => setForm({...form, role: e.target.value, new_secretariat_nom: '', new_secretariat_type: ''})}>
                      {(userTab === 'auditeurs' ? ['AUDITEUR'] : userTab === 'formateurs' ? ['FORMATEUR'] : staffRoleOptions).map(r => <option key={r} value={r}>{roleLabel(r)}</option>)}
                    </select>
                    {form.role === 'CHEF_INJS_ADMIN' && users.some(u => u.role === 'CHEF_INJS_ADMIN') && (
                      <small className="text-danger"><i className="bi bi-exclamation-triangle me-1"></i>Un Chef INJS Admin existe déjà. Ce rôle est unique sur la plateforme.</small>
                    )}
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">{matriculeLabel}</label>
                  <input type="text" className="form-control" value={form.matricule} onChange={e => setForm({...form, matricule: e.target.value})} placeholder={userTab === 'formateurs' ? 'Ex. F0042' : undefined} />
                  {userTab === 'formateurs' && (
                    <small className="text-muted">Doit correspondre au N° badge de l'enseignant dans le référentiel.</small>
                  )}
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Adresse e-mail</label>
                    <input type="email" className="form-control" value={form.email} onChange={e => setForm({...form, email: e.target.value})} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Téléphone</label>
                    <input type="text" className="form-control" value={form.telephone} onChange={e => setForm({...form, telephone: e.target.value})} />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Mot de passe *</label>
                  <input type="password" className="form-control" required value={form.password} onChange={e => setForm({...form, password: e.target.value})} />
                </div>
                {!['SECRETARIAT', 'CHEF_SECRETARIAT'].includes(currentUser?.role) && !['CHEF_INJS_ADMIN', 'INJS_ADMIN', 'ENCADRANT'].includes(form.role) && (
                  <div className="form-group">
                    <label className="form-label">Secrétariat</label>
                    <select className="form-control" value={form.secretariat} onChange={e => setForm({...form, secretariat: e.target.value})}>
                      <option value="">-- Aucun --</option>
                      {secretariats.map(s => (
                        <option key={s.id} value={s.id}>{s.nom}</option>
                      ))}
                    </select>
                    {form.role === 'CHEF_SECRETARIAT' && form.secretariat && users.some(u => u.role === 'CHEF_SECRETARIAT' && String(u.secretariat) === String(form.secretariat)) && (
                      <small className="text-danger"><i className="bi bi-exclamation-triangle me-1"></i>Ce secrétariat a déjà un Chef Secrétariat.</small>
                    )}
                  </div>
                )}
                {!['SECRETARIAT', 'CHEF_SECRETARIAT'].includes(currentUser?.role) && form.role === 'SECRETARIAT' && !form.secretariat && (
                  <div style={{ background: '#f0f7ff', border: '1px solid #bcd', borderRadius: 6, padding: '0.6rem 0.75rem' }}>
                    <p className="text-muted small" style={{ fontWeight: 600, marginBottom: '0.4rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      <i className="bi bi-building-add me-1"></i>Ou créer un nouveau secrétariat
                    </p>
                    <div className="grid-2">
                      <div className="form-group">
                        <label className="form-label">Nom</label>
                        <input type="text" className="form-control" value={form.new_secretariat_nom}
                          onChange={e => setForm({...form, new_secretariat_nom: e.target.value})} />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Type</label>
                        <select className="form-control" value={form.new_secretariat_type} onChange={e => setForm({...form, new_secretariat_type: e.target.value})}>
                          <option value="">-- Sélectionner --</option>
                          <option value="A">Type A (grades A1, A2, A3…)</option>
                          <option value="B">Type B (grades B1, B2, B3…)</option>
                          <option value="C">Type C (grades C1, C2, C3…)</option>
                        </select>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Annuler</button>
                <button type="submit" className="btn btn-dfrc" disabled={saving}>{saving ? 'Création...' : 'Créer'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit User Modal */}
      {showEditModal && editingUser && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="modal-content" style={{ maxHeight: 'calc(100vh - 3rem)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-pencil-square me-2"></i>Modifier — {editingUser.username}</h5>
              <button className="btn-close" onClick={() => setShowEditModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleEdit} style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <div className="modal-body" style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
                {editError && <div className="alert alert-danger" style={{ whiteSpace: 'pre-line' }}>{String(editError).replaceAll('CPFAE', 'INJS')}</div>}
                <div className="form-group">
                  <label className="form-label">Rôle</label>
                  <select
                    className="form-control"
                    value={editForm.role}
                    onChange={e => setEditForm({...editForm, role: e.target.value})}
                    disabled={!creatableRoles.includes(editingUser?.role)}
                  >
                    {creatableRoles.map(r => (
                      <option key={r} value={r}>{roleLabel(r)}</option>
                    ))}
                  </select>
                  {!creatableRoles.includes(editingUser?.role) && (
                    <small className="text-warning"><i className="bi bi-lock me-1"></i>Rôle protégé — modification impossible.</small>
                  )}
                  {editForm.role === 'CHEF_INJS_ADMIN' && users.some(u => u.role === 'CHEF_INJS_ADMIN' && u.id !== editingUser?.id) && (
                    <small className="text-danger"><i className="bi bi-exclamation-triangle me-1"></i>Un Chef INJS Admin existe déjà. Ce rôle est unique sur la plateforme.</small>
                  )}
                  {editForm.role === 'CHEF_SECRETARIAT' && editForm.secretariat && (() => {
                    const secId = String(editForm.secretariat)
                    const hasChef = users.some(u => u.role === 'CHEF_SECRETARIAT' && String(u.secretariat) === secId && u.id !== editingUser?.id)
                    return hasChef ? (
                      <small className="text-danger"><i className="bi bi-exclamation-triangle me-1"></i>Ce secrétariat a déjà un Chef Secrétariat.</small>
                    ) : null
                  })()}
                </div>
                {currentUser?.role !== 'SECRETARIAT' && !['CHEF_INJS_ADMIN', 'INJS_ADMIN', 'ENCADRANT'].includes(editForm.role) && (
                  <div className="form-group">
                    <label className="form-label">Secrétariat</label>
                    <select className="form-control" value={editForm.secretariat} onChange={e => setEditForm({...editForm, secretariat: e.target.value})}>
                      <option value="">-- Aucun --</option>
                      {secretariats.map(s => (
                        <option key={s.id} value={s.id}>{s.nom}</option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="form-group">
                  <label className="form-label">Nom d'utilisateur *</label>
                  <input type="text" className="form-control" required value={editForm.username} onChange={e => setEditForm({...editForm, username: e.target.value})} />
                </div>
                <div className="form-group">
                  <label className="form-label">N° Matricule (badge)</label>
                  <input type="text" className="form-control" value={editForm.matricule} onChange={e => setEditForm({...editForm, matricule: e.target.value})} />
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Prénom</label>
                    <input type="text" className="form-control" value={editForm.first_name} onChange={e => setEditForm({...editForm, first_name: e.target.value})} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Nom</label>
                    <input type="text" className="form-control" value={editForm.last_name} onChange={e => setEditForm({...editForm, last_name: e.target.value})} />
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Adresse e-mail</label>
                    <input type="email" className="form-control" value={editForm.email} onChange={e => setEditForm({...editForm, email: e.target.value})} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Téléphone</label>
                    <input type="text" className="form-control" value={editForm.telephone} onChange={e => setEditForm({...editForm, telephone: e.target.value})} />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Statut</label>
                  <select className="form-control" value={editForm.is_active ? 'true' : 'false'}
                    onChange={e => setEditForm({...editForm, is_active: e.target.value === 'true'})}>
                    <option value="true">Actif</option>
                    <option value="false">Inactif</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Nouveau mot de passe <small className="text-muted">(laisser vide pour ne pas changer)</small></label>
                  <input type="password" className="form-control" value={editForm.password}
                    onChange={e => setEditForm({...editForm, password: e.target.value})} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowEditModal(false)}>Annuler</button>
                <button type="submit" className="btn btn-dfrc" disabled={saving}>{saving ? 'Enregistrement...' : 'Enregistrer'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
