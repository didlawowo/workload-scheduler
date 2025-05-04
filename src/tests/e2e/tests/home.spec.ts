import { test, expect } from '@playwright/test';

test('page accueil', async ({ page }) => {
    // Aller sur la page d'accueil
    await page.goto('http://127.0.0.1:8000');

    await expect(page).toHaveTitle('Kubernetes Workloads Manager');
    // await page.getByTestId('shutdown-all').click();
    // await page.getByTestId('scale-up-all').click();

    await page.getByPlaceholder('Rechercher par nom ou namespace...').fill('guestbook-ui3');
    // await page.getByTestId('search').click();

    // Log pour debug
    console.log('Page chargée avec succès');
});

test('manage status deployment', async ({ page }) => {
    await page.goto('http://127.0.0.1:8000');

    await page.getByTestId('shutdown').click();

    console.log('Page chargée avec succès');
});