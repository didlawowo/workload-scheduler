const modal = document.getElementById('cronModal');
const closeBtn = document.querySelector('.close');
const cancelBtn = document.getElementById('cancelBtn');
const saveBtn = document.getElementById('saveBtn');
const cronStart = document.getElementById('cronExpressionStart');
const cronStop = document.getElementById('cronExpressionStop');
const cronError = document.getElementById('cronError');

const actionTypeEl = document.getElementById('actionType');
const resourceNameEl = document.getElementById('resourceName');
const namespaceNameEl = document.getElementById('namespaceName');
const directionTypeEl = document.getElementById('directionType');


/* main */

function toggleWorkloadDetails(button) {
    const podDetails = button.closest('.pod-details');
    podDetails.classList.toggle('collapsed');
    button.textContent = podDetails.classList.contains('collapsed') ? 'Show Details' : 'Hide Details';
}

function manageWorkloadStatus(type, name, namespace, action) {
    let url = ``;
    if (action === 'down') {
        url = `/shutdown/${type}/${namespace}/${name}`;
    } else if (action === 'up') {
        url = `/up/${type}/${namespace}/${name}`;
    } else if (action === 'down-all') {
        url = `/manage-all/down`;
    } else if (action === 'up-all') {
        url = `/manage-all/up`;
    }
    fetch(url, { method: 'GET' })
        .then(response => response.json())
        .then(data => {
            window.location.reload();
        })
        .catch(error => console.error('Error:', error));
}

/* modal management */

// Fonction pour fermer le modal et réinitialiser son état
function closeModal() {
    modal.style.display = 'none';
    saveBtn.dataset.mode = 'create';
    document.querySelector('.modal-content h3').textContent = 'Éditeur d\'expression Cron';
    currentScheduleId = null;
}
closeBtn.addEventListener('click', closeModal);
cancelBtn.addEventListener('click', closeModal);

window.addEventListener('click', (event) => {
    if (event.target === modal) {
        closeModal();
    }
});

/* crontab management */
let defaultCronValue = "*/5 * * * *";
let currentCronStartValue = defaultCronValue;
let currentCronStopValue = defaultCronValue;
let currentAction, currentName, currentNamespace, currentDirection, currentUid;
let currentScheduleId = null;

function isValidCron(expression) {
    const pattern = /^(\*|([0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])|\*\/([0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])) (\*|([0-9]|1[0-9]|2[0-3])|\*\/([0-9]|1[0-9]|2[0-3])) (\*|([1-9]|1[0-9]|2[0-9]|3[0-1])|\*\/([1-9]|1[0-9]|2[0-9]|3[0-1])) (\*|([1-9]|1[0-2])|\*\/([1-9]|1[0-2])) (\*|([0-6])|\*\/([0-6]))$/;
    return pattern.test(expression);
}

// Fonction pour éditer une programmation
function edit_prog(uid) {
    fetch('/schedules/uid', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(schedules => {
        if (existingWorkload) {
            currentScheduleId = existingWorkload.id;
            currentUid = existingWorkload.uid;
            cronStart.value = existingWorkload.cron_start || defaultCronValue;
            cronStop.value = existingWorkload.cron_stop || defaultCronValue;
            document.querySelector('.modal-content h3').textContent = 'Modifier la programmation';
            saveBtn.dataset.mode = 'update';
        } else {
            currentScheduleId = null;
            cronStart.value = defaultCronValue;
            cronStop.value = defaultCronValue;
            document.querySelector('.modal-content h3').textContent = 'Nouvelle programmation';
            saveBtn.dataset.mode = 'create';
        }
        
        cronError.style.display = 'none';
        modal.style.display = 'block';
    })
    .catch(error => {
        console.error('Erreur lors de la vérification des programmations:', error);
        currentScheduleId = null;
        cronStart.value = defaultCronValue;
        cronStop.value = defaultCronValue;
        document.querySelector('.modal-content h3').textContent = 'Nouvelle programmation';
        saveBtn.dataset.mode = 'create';
        cronError.style.display = 'none';
        modal.style.display = 'block';
    });
}

// Charger les programmations au chargement de la page
document.addEventListener("DOMContentLoaded", function() {
    getListSchedule();
    
    var progressBar = document.getElementById("progressBar");
    var width = 1;
    var interval = setInterval(function() {
        if (width >= 100) {
            clearInterval(interval);
            progressBar.style.display = 'none';
        } else {
            width++;
            progressBar.style.width = width + '%';
        }
    }, 10);
});

// Mettre à jour le gestionnaire d'événements pour le bouton "saveBtn"
saveBtn.addEventListener('click', () => {
    const cron_start_value = cronStart.value.trim();
    const cron_stop_value = cronStop.value.trim();
    if (!isValidCron(cron_start_value) || (!isValidCron(cron_stop_value))){
        cronError.style.display = 'block';
        return;
    }

    currentCronStartValue = cron_start_value;
    currentCronStopValue = cron_stop_value;

    const isUpdate = saveBtn.dataset.mode === 'update';
    const workloadName = `${currentAction}-${currentName}-${currentDirection}`;

    const now = new Date();
    const oneYearLater = new Date();
    oneYearLater.setFullYear(now.getFullYear() + 1);

    if (isUpdate && currentScheduleId) {
        fetch(`/schedules/${currentScheduleId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: currentScheduleId,
                cron_start: currentCronStartValue,
                cron_stop: currentCronStopValue,
                name: workloadName,
                uid: currentUid,
                active: true
            })
        })
        .then(response => response.json())
        .then(data => {
            console.log('Programmation mise à jour:', data);
            getListSchedule();
            closeModal();
        })
        .catch(error => {
            console.error('Erreur lors de la mise à jour de la programmation:', error);
            alert(`Erreur lors de la mise à jour de la programmation: ${error.message}`);
        });
    } else {
        fetch('/schedules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: workloadName,
                uid: currentUid,
                cron_start: currentCronStartValue,
                cron_stop: currentCronStopValue,
                status: "scheduled",
                active: true,
                resource_type: currentAction,
                resource_name: currentName,
                resource_namespace: currentNamespace,
                direction: currentDirection
            })
        })
        .then(response => response.json())
        .then(data => {
            console.log('Programmation créée:', data);
            getListSchedule();
            closeModal();
        })
        .catch(error => {
            console.error('Erreur lors de la création de la programmation:', error);
            alert(`Erreur lors de la création de la programmation: ${error.message}`);
        });
    }
});

// Fonction pour récupérer les programmations depuis l'API
function getListSchedule() {
    fetch('/schedules', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Erreur réseau: ' + response.status);
        }
        return response.json();
    })
    .catch(error => {
        console.error('Erreur lors de la récupération des programmations:', error);
    });
}

// Fonction pour supprimer une programmation
function deleteSchedule(scheduleId) {
    if (confirm('Êtes-vous sûr de vouloir supprimer cette programmation ?')) {
        fetch(`/schedules/${scheduleId}`, {
            method: 'DELETE'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Erreur réseau: ' + response.status);
            }
            return response.json();
        })
        .then(data => {
            console.log('Programmation supprimée:', data);
            getListSchedule();
        })
        .catch(error => {
            console.error('Erreur lors de la suppression de la programmation:', error);
        });
    }
}

// Fonction pour éditer un workload existant depuis le tableau
function editWorkload(scheduleId, cronValue) {
    currentScheduleId = scheduleId;

    cronStart.value = cronValue === 'Non programmé' ? defaultCronValue : cronValue;
    cronError.style.display = 'none';

    document.querySelector('.modal-content h3').textContent = 'Modifier la programmation';

    saveBtn.dataset.mode = 'update';

    modal.style.display = 'block';
}