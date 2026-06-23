// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightLlmsTxt from 'starlight-llms-txt';
import { visit } from 'unist-util-visit';

const BASE = '/nxstate';

// Starlight base-prefixes its own nav + assets, but NOT hand-written absolute links in Markdown
// content. This rehype plugin prefixes internal `/...` links with the base so cross-links work
// on a GitHub Pages project site — while keeping source links clean/portable (`/guides/x/`).
function rehypeBaseLinks() {
	return (/** @type {any} */ tree) => {
		visit(tree, 'element', (/** @type {any} */ node) => {
			if (node.tagName !== 'a') return;
			const href = node.properties?.href;
			if (typeof href !== 'string') return;
			if (href.startsWith('/') && !href.startsWith('//') && !href.startsWith(BASE + '/') && href !== BASE) {
				node.properties.href = BASE + href;
			}
		});
	};
}

// https://astro.build/config
export default defineConfig({
	// GitHub Pages project site — REQUIRED for correct llms.txt + sitemap + asset links.
	site: 'https://rnwolfe.github.io',
	base: BASE,
	markdown: { rehypePlugins: [rehypeBaseLinks] },

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
						{ label: 'Installation', slug: 'getting-started/installation' },
						{ label: 'Quickstart', slug: 'getting-started/quickstart' },
					],
				},
				{ label: 'Concepts', items: [{ autogenerate: { directory: 'concepts' } }] },
				{ label: 'Guides', items: [{ autogenerate: { directory: 'guides' } }] },
				{ label: 'Reference', items: [{ autogenerate: { directory: 'reference' } }] },
				{ label: 'Contributing', slug: 'contributing' },
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
