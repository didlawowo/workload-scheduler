"""
Script de test d'intégration pour vérifier le fonctionnement d'ArgoCD
Ce script teste la désactivation/activation de l'auto-sync ArgoCD
"""

import os
import sys
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.argocd import ArgoTokenManager, patch_argocd_application
from loguru import logger

# Configure logger for testing
logger.remove()
logger.add(sys.stdout, level="DEBUG", format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

def test_argocd_connection():
    """Test 1: Vérifier la connexion à ArgoCD"""
    print("\n" + "="*80)
    print("TEST 1: Vérification de la connexion à ArgoCD")
    print("="*80)

    try:
        token_manager = ArgoTokenManager()
        token = token_manager.get_token()

        if token and len(token) > 0:
            logger.success(f"✅ Connexion réussie - Token obtenu (longueur: {len(token)})")
            return True
        else:
            logger.error("❌ Échec - Token vide ou invalide")
            return False
    except Exception as e:
        logger.error(f"❌ Échec de connexion: {e}")
        return False

def test_get_application_info(app_name):
    """Test 2: Récupérer les informations d'une application"""
    print("\n" + "="*80)
    print(f"TEST 2: Récupération des informations de l'application '{app_name}'")
    print("="*80)

    try:
        import requests
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        token_manager = ArgoTokenManager()
        token = token_manager.get_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        res = requests.get(
            f"{token_manager.ARGOCD_API_URL}/applications/{app_name}",
            headers=headers,
            timeout=5,
            verify=False
        )

        if res.status_code == 200:
            app_data = res.json()
            logger.success(f"✅ Application trouvée: {app_name}")

            # Check auto-sync status
            sync_policy = app_data.get("spec", {}).get("syncPolicy", {})
            auto_sync_enabled = "automated" in sync_policy

            logger.info(f"   └─ Auto-sync actuellement: {'ACTIVÉ' if auto_sync_enabled else 'DÉSACTIVÉ'}")

            if auto_sync_enabled:
                automated = sync_policy["automated"]
                logger.info(f"      └─ Prune: {automated.get('prune', False)}")
                logger.info(f"      └─ SelfHeal: {automated.get('selfHeal', False)}")

            return True, auto_sync_enabled
        elif res.status_code == 404:
            logger.error(f"❌ Application '{app_name}' non trouvée")
            logger.info("   Liste des applications disponibles:")

            # List available applications
            res_list = requests.get(
                f"{token_manager.ARGOCD_API_URL}/applications",
                headers=headers,
                timeout=5,
                verify=False
            )

            if res_list.status_code == 200:
                apps = res_list.json().get("items", [])
                for app in apps[:10]:  # Show first 10
                    logger.info(f"      - {app['metadata']['name']}")

            return False, None
        else:
            logger.error(f"❌ Erreur API: {res.status_code} - {res.text}")
            return False, None

    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération: {e}")
        return False, None

def test_disable_auto_sync(app_name):
    """Test 3: Désactiver l'auto-sync"""
    print("\n" + "="*80)
    print(f"TEST 3: Désactivation de l'auto-sync pour '{app_name}'")
    print("="*80)

    try:
        # Get current state
        success, current_state = test_get_application_info(app_name)
        if not success:
            logger.error("❌ Impossible de continuer - application non trouvée")
            return False

        if not current_state:
            logger.warning("⚠️  Auto-sync déjà désactivé - test skip")
            return True

        # Disable auto-sync
        logger.info("🔧 Tentative de désactivation de l'auto-sync...")
        patch_argocd_application(app_name, enable_auto_sync=False)

        # Verify it was disabled
        import time
        time.sleep(2)  # Wait a bit for the change to propagate

        success, new_state = test_get_application_info(app_name)
        if success and not new_state:
            logger.success("✅ Auto-sync désactivé avec succès")
            return True
        else:
            logger.error("❌ Auto-sync n'a pas été désactivé")
            return False

    except Exception as e:
        logger.error(f"❌ Erreur lors de la désactivation: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_enable_auto_sync(app_name):
    """Test 4: Activer l'auto-sync"""
    print("\n" + "="*80)
    print(f"TEST 4: Activation de l'auto-sync pour '{app_name}'")
    print("="*80)

    try:
        # Get current state
        success, current_state = test_get_application_info(app_name)
        if not success:
            logger.error("❌ Impossible de continuer - application non trouvée")
            return False

        if current_state:
            logger.warning("⚠️  Auto-sync déjà activé - test skip")
            return True

        # Enable auto-sync
        logger.info("🔧 Tentative d'activation de l'auto-sync...")
        patch_argocd_application(app_name, enable_auto_sync=True)

        # Verify it was enabled
        import time
        time.sleep(2)  # Wait a bit for the change to propagate

        success, new_state = test_get_application_info(app_name)
        if success and new_state:
            logger.success("✅ Auto-sync activé avec succès")
            return True
        else:
            logger.error("❌ Auto-sync n'a pas été activé")
            return False

    except Exception as e:
        logger.error(f"❌ Erreur lors de l'activation: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("🧪 TESTS D'INTÉGRATION ARGOCD")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # Get app name from environment or use default
    app_name = os.getenv("ARGOCD_TEST_APP", "")

    if not app_name:
        logger.warning("⚠️  Variable ARGOCD_TEST_APP non définie")
        logger.info("Utilisation: ARGOCD_TEST_APP=nom-application python test_argocd_integration.py")
        logger.info("\nRécupération de la liste des applications disponibles...")

        try:
            import requests
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            token_manager = ArgoTokenManager()
            token = token_manager.get_token()
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            res = requests.get(
                f"{token_manager.ARGOCD_API_URL}/applications",
                headers=headers,
                timeout=5,
                verify=False
            )

            if res.status_code == 200:
                apps = res.json().get("items", [])
                logger.info(f"\n📋 Applications disponibles ({len(apps)}):")
                for app in apps:
                    sync_policy = app.get("spec", {}).get("syncPolicy", {})
                    auto_sync = "✓" if "automated" in sync_policy else "✗"
                    logger.info(f"   [{auto_sync}] {app['metadata']['name']}")

                if apps:
                    app_name = apps[0]['metadata']['name']
                    logger.info(f"\n🎯 Utilisation de la première application: {app_name}")
                else:
                    logger.error("❌ Aucune application trouvée")
                    return
            else:
                logger.error(f"❌ Erreur lors de la récupération des applications: {res.status_code}")
                return
        except Exception as e:
            logger.error(f"❌ Erreur: {e}")
            return

    results = {
        "connection": False,
        "get_info": False,
        "disable_sync": False,
        "enable_sync": False
    }

    # Test 1: Connection
    results["connection"] = test_argocd_connection()
    if not results["connection"]:
        logger.error("\n❌ Tests arrêtés - impossible de se connecter à ArgoCD")
        return

    # Test 2: Get application info
    results["get_info"], initial_state = test_get_application_info(app_name)
    if not results["get_info"]:
        logger.error("\n❌ Tests arrêtés - application non trouvée")
        return

    # Test 3 & 4: Toggle auto-sync
    if initial_state:
        # Currently enabled, test disable then re-enable
        results["disable_sync"] = test_disable_auto_sync(app_name)
        results["enable_sync"] = test_enable_auto_sync(app_name)
    else:
        # Currently disabled, test enable then disable
        results["enable_sync"] = test_enable_auto_sync(app_name)
        results["disable_sync"] = test_disable_auto_sync(app_name)

    # Summary
    print("\n" + "="*80)
    print("📊 RÉSUMÉ DES TESTS")
    print("="*80)

    total = len(results)
    passed = sum(1 for v in results.values() if v)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print("\n" + "-"*80)
    print(f"Total: {passed}/{total} tests passés ({passed*100//total}%)")
    print("="*80)

    if passed == total:
        logger.success("\n🎉 Tous les tests sont passés!")
    else:
        logger.error(f"\n⚠️  {total - passed} test(s) en échec")

if __name__ == "__main__":
    main()
