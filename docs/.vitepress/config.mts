import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'klaus',
  description: 'Multi-agent AI assistant platform with local model support and dynamic MCP integration',
  base: '/klaus/',

  ignoreDeadLinks: [
    /localhost/,
  ],

  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/klaus/logo.svg' }],
    ['meta', { name: 'theme-color', content: '#78716c' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:title', content: 'klaus' }],
    ['meta', { property: 'og:description', content: 'Multi-agent AI assistant platform' }],
  ],

  themeConfig: {
    logo: '/logo.svg',

    nav: [
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'Reference', link: '/reference/api' },
      {
        text: 'GitHub',
        link: 'https://github.com/hybridx/klaus',
      },
    ],

    sidebar: {
      '/guide/': [
        {
          text: 'Introduction',
          items: [
            { text: 'Getting Started', link: '/guide/getting-started' },
            { text: 'Architecture', link: '/guide/architecture' },
          ],
        },
        {
          text: 'Extending klaus',
          items: [
            { text: 'Adding Tools', link: '/guide/adding-tools' },
            { text: 'Adding Model Backends', link: '/guide/adding-backends' },
            { text: 'Adding UI Pages', link: '/guide/ui-guide' },
          ],
        },
        {
          text: 'Deep Dives',
          items: [
            { text: 'Memory System', link: '/guide/memory-system' },
            { text: 'Task Routing', link: '/guide/task-routing' },
          ],
        },
      ],
      '/reference/': [
        {
          text: 'Reference',
          items: [
            { text: 'API Reference', link: '/reference/api' },
            { text: 'WebSocket Protocol', link: '/reference/websocket' },
            { text: 'Configuration', link: '/reference/configuration' },
            { text: 'Database Schema', link: '/reference/database' },
          ],
        },
      ],
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/hybridx/klaus' },
    ],

    search: {
      provider: 'local',
    },

    editLink: {
      pattern: 'https://github.com/hybridx/klaus/edit/main/docs/:path',
      text: 'Edit this page on GitHub',
    },

    footer: {
      message: 'Released under the MIT License.',
      copyright: 'Built with VitePress',
    },

    outline: {
      level: [2, 3],
    },
  },
})
