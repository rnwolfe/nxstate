// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightLlmsTxt from 'starlight-llms-txt';

// https://astro.build/config
export default defineConfig({
	// Canonical deploy URL — REQUIRED for correct llms.txt + sitemap links.
	site: 'https://docs.nxstate.labs.rwolfe.io',

	integrations: [
		starlight({
			title: 'nxstate',
			description:
				'Read-only Cisco Nexus (NX-OS) state-gathering CLI for agents and humans.',
			social: [
				{ icon: 'github', label: 'GitHub', href: 'https://github.com/rnwolfe/nxstate' },
			],
			editLink: { baseUrl: 'https://github.com/rnwolfe/nxstate/edit/main/docs-site/' },
			lastUpdated: true,
			customCss: ['./src/styles/custom.css'],
			expressiveCode: {
				themes: ['github-dark', 'github-light'],
				styleOverrides: { borderRadius: '0.5rem' },
			},
			sidebar: [
				{
					label: 'Start here',
					items: [
						{ label: 'Introduction', slug: 'index' },
						{ label: 'Quickstart', slug: 'getting-started/quickstart' },
					],
				},
				{ label: 'Guides', items: [{ autogenerate: { directory: 'guides' } }] },
				{ label: 'Reference', items: [{ autogenerate: { directory: 'reference' } }] },
			],
			plugins: [
				starlightLlmsTxt({
					projectName: 'nxstate',
					description:
						'Read-only Cisco Nexus (NX-OS) state-gathering CLI. Runs show commands as ' +
						'clean JSON across one switch or a fleet; cannot configure a device ' +
						'(WRITE_REFUSED). Built for LLM agents: structured output, schema ' +
						'self-description, inventory-driven multi-device fan-out.',
					exclude: ['changelog', 'legal/**'],
				}),
			],
		}),
	],
});
