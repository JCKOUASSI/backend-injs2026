/** @type {import('eslint').Linter.Config} */
module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
  },
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
  ],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  settings: {
    react: { version: 'detect' },
  },
  ignorePatterns: ['dist', 'node_modules', 'build', 'coverage'],
  rules: {
    'react/react-in-jsx-scope': 'off',
    'react/prop-types': 'off',
    'react/no-unescaped-entities': 'off',
    'react-hooks/exhaustive-deps': 'warn',
    'no-unused-vars': [
      'warn',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
    ],
    'no-empty': ['error', { allowEmptyCatch: true }],
    'no-irregular-whitespace': 'warn',
  },
  overrides: [
    {
      // Fichiers de tests et harnais Vitest/Testing Library.
      files: ['src/test/**/*.{js,jsx}', 'src/**/*.test.{js,jsx}', 'src/**/*.spec.{js,jsx}'],
      globals: {
        describe: 'readonly',
        it: 'readonly',
        test: 'readonly',
        expect: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        vi: 'readonly',
        // process.cwd() / process.env dans les tests Node (lecture de fichiers,
        // résolution de racines). 'no-undef' reste active : seul le global
        // Node est déclaré, la règle n'est ni désactivée ni contournée.
        process: 'readonly',
      },
      rules: {
        // Les tests utilisent volontairement des assertions et du JSX.
        'react/display-name': 'off',
      },
    },
  ],
}
