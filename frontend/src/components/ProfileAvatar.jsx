import { useEffect, useState } from 'react'
import api from '../services/api'

/** Avatar du compte connecté : récupère la photo via l'API authentifiée. */
export default function ProfileAvatar({ photoUrl, initials = '?', name = 'profil', size = 48 }) {
  const [src, setSrc] = useState('')

  useEffect(() => {
    let active = true
    let objectUrl = ''
    setSrc('')
    if (photoUrl) {
      api.getBlob(photoUrl)
        .then(({ blob }) => {
          if (!active) return
          objectUrl = URL.createObjectURL(blob)
          setSrc(objectUrl)
        })
        .catch(() => { if (active) setSrc('') })
    }
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [photoUrl])

  const circleStyle = {
    width: size,
    height: size,
    borderRadius: '50%',
    overflow: 'hidden',
    background: 'linear-gradient(135deg, #071B3A 0%, #1267D6 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#fff',
    fontWeight: 700,
    flexShrink: 0,
  }

  return (
    <div style={circleStyle} role="img" aria-label={`Photo de ${name}`}>
      {src
        ? <img src={src} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        : <span aria-hidden="true">{initials || '?'}</span>}
    </div>
  )
}
