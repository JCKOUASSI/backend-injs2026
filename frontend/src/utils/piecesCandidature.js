// Aligné sur EXTENSIONS_PIECE_CANDIDATURE et TAILLE_MAX_PIECE (backend/core/validators.py).
// Ne PAS accepter les archives génériques, fichiers exécutables ou HTML.
export const FORMATS_PIECES_CANDIDATURE = [
  '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.heic', '.heif',
  '.doc', '.docx', '.odt', '.rtf', '.txt', '.csv', '.xls', '.xlsx', '.ods', '.ppt', '.pptx', '.odp',
].join(',')
export const AIDE_PIECES_CANDIDATURE = 'Documents PDF, Word, OpenDocument, Excel, texte, CSV, PowerPoint et images courantes (10 Mio maximum). Les exécutables, pages HTML et archives ZIP ne sont pas acceptés'
