import { defineCollection } from 'astro:content';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';
import { z } from 'astro:content';

export const collections = {
	docs: defineCollection({
		loader: docsLoader(),
		schema: docsSchema({
			extend: z.object({
				// Page owner — used for staleness triage.
				owner: z.string().optional(),
				// Last manual review date — feeds a "pages older than N months" check.
				lastReviewed: z.coerce.date().optional(),
			}),
		}),
	}),
};
