import js from '@eslint/js';
import pluginVue from 'eslint-plugin-vue';
import globals from 'globals';
import tseslint from 'typescript-eslint';

const typescriptRules = tseslint.configs.recommended.reduce(
  (rules, config) => ({ ...rules, ...config.rules }),
  {},
);

const browserAndNodeGlobals = {
  ...globals.browser,
  ...globals.node,
};

export default [
  {
    ignores: ['dist', 'node_modules', 'coverage'],
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parser: tseslint.parser,
      globals: browserAndNodeGlobals,
    },
    plugins: {
      '@typescript-eslint': tseslint.plugin,
    },
    rules: {
      ...typescriptRules,
      '@typescript-eslint/consistent-type-imports': 'error',
    },
  },
  {
    files: ['**/*.vue'],
    languageOptions: {
      globals: browserAndNodeGlobals,
      parserOptions: {
        parser: tseslint.parser,
      },
    },
    plugins: {
      '@typescript-eslint': tseslint.plugin,
    },
    rules: {
      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': 'error',
      'vue/multi-word-component-names': 'off',
    },
  },
];
