import { defineConfig, devices } from '@playwright/test';
import dotenv from 'dotenv';

// Lecture du fichier .env
dotenv.config();

const config = defineConfig({
    testDir: './tests',
    timeout: 30 * 1000,
    expect: {
        timeout: 5000
    },
    fullyParallel: true,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 2 : 0,
    workers: process.env.CI ? 1 : undefined,
    reporter: 'html',
    use: {
        actionTimeout: 0,
        baseURL: process.env.BASE_URL || 'http://127.0.0.1:8000',
        trace: 'on-first-retry',
        video: 'on-first-retry',
    },

    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        }
    ],

    outputDir: 'test-results/',
});

export default config;