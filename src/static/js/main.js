const modal = document.getElementById('cronModal');
const closeBtn = document.querySelector('.close');
const cancelBtn = document.getElementById('cancelBtn');
const saveBtn = document.getElementById('saveBtn');
const cronInput = document.getElementById('cronExpression');
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
let currentCronValue = defaultCronValue;
let currentAction, currentName, currentNamespace, currentDirection;
let currentScheduleId = null;

function isValidCron(expression) {
    const pattern = /^(\*|([0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])|\*\/([0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])) (\*|([0-9]|1[0-9]|2[0-3])|\*\/([0-9]|1[0-9]|2[0-3])) (\*|([1-9]|1[0-9]|2[0-9]|3[0-1])|\*\/([1-9]|1[0-9]|2[0-9]|3[0-1])) (\*|([1-9]|1[0-2])|\*\/([1-9]|1[0-2])) (\*|([0-6])|\*\/([0-6]))$/;
    return pattern.test(expression);
}

// Fonction pour éditer une programmation (appelée par le bouton Programme)
function edit_prog(action, name, namespace, direction) {
    currentAction = action;
    currentName = name;
    currentNamespace = namespace;
    currentDirection = direction;
    
    actionTypeEl.textContent = action;
    resourceNameEl.textContent = name;
    namespaceNameEl.textContent = namespace;
    directionTypeEl.textContent = direction;
    
    const workloadName = `${action}-${name}-${direction}`;
    
    fetch('/schedules', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(schedules => {
        const existingWorkload = schedules.find(schedule => 
            schedule.name === workloadName || 
            (schedule.name.includes(name) && 
             schedule.name.includes(action) && 
             schedule.name.includes(direction)));
        
        if (existingWorkload) {
            currentScheduleId = existingWorkload.id;
            cronInput.value = existingWorkload.cron || defaultCronValue;
            
            document.querySelector('.modal-content h3').textContent = 'Modifier la programmation';
            saveBtn.dataset.mode = 'update';
        } else {
            currentScheduleId = null;
            cronInput.value = defaultCronValue;
            
            document.querySelector('.modal-content h3').textContent = 'Nouvelle programmation';
            saveBtn.dataset.mode = 'create';
        }
        
        cronError.style.display = 'none';
        modal.style.display = 'block';
    })
    .catch(error => {
        console.error('Erreur lors de la vérification des programmations:', error);
        currentScheduleId = null;
        cronInput.value = defaultCronValue;
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
    const expression = cronInput.value.trim();
    
    if (!isValidCron(expression)) {
        cronError.style.display = 'block';
        return;
    }
    
    currentCronValue = expression;
    
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
                cron: currentCronValue,
                name: workloadName,
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
                start_time: now.toISOString(),
                end_time: oneYearLater.toISOString(),
                cron: currentCronValue,
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


cronInput.addEventListener('input', () => {
    const expression = cronInput.value.trim();
    if (expression && !isValidCron(expression)) {
        cronError.style.display = 'block';
    } else {
        cronError.style.display = 'none';
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
    .then(data => {
        console.log('Programmations récupérées:', data);
        if (Array.isArray(data)) {
            displayWorkloads(data);
        } else {
            console.error('Format de données inattendu:', data);
        }
    })
    .catch(error => {
        console.error('Erreur lors de la récupération des programmations:', error);
    });
}

// Mettre à jour la fonction displaySchedules pour montrer plus d'informations
function displayWorkloads(schedules) {
    const schedulesContainer = document.getElementById('schedulesContainer');
    
    if (!schedulesContainer) {
        console.error("L'élément 'schedulesContainer' n'existe pas dans le DOM");
        return;
    }
    
    schedulesContainer.innerHTML = '';
    
    if (schedules.length === 0) {
        schedulesContainer.innerHTML = '<p>Aucune programmation trouvée</p>';
        return;
    }
    
    const table = document.createElement('table');
    table.innerHTML = `
        <thead>
            <tr>
                <th>Nom</th>
                <th>Resource</th>
                <th>Namespace</th>
                <th>Action</th>
                <th>Date début</th>
                <th>Date fin</th>
                <th>Statut</th>
                <th>Expression Cron</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody id="schedulesTableBody">
        </tbody>
    `;
    
    const tableBody = table.querySelector('#schedulesTableBody');
    
    // Parcourez les programmations et les ajoute au tableau
    schedules.forEach(schedule => {
        const row = document.createElement('tr');
        
        let resourceType = schedule.resource_type || '';
        let resourceName = schedule.resource_name || '';
        let resourceNamespace = schedule.resource_namespace || '';
        let direction = schedule.direction || '';
        
        if (!resourceType || !resourceName || !direction) {
            const nameParts = schedule.name.split('-');
            if (nameParts.length >= 3) {
                resourceType = resourceType || nameParts[0];
                resourceName = resourceName || nameParts.slice(1, -1).join('-');
                direction = direction || nameParts[nameParts.length - 1];
            }
        }
        
        const startDate = new Date(schedule.start_time).toLocaleString();
        const endDate = new Date(schedule.end_time).toLocaleString();
        
        const cronExpression = schedule.cron ? schedule.cron : 'Non programmé';
        
        row.innerHTML = `
            <td>${schedule.name}</td>
            <td>${resourceName}</td>
            <td>${resourceNamespace}</td>
            <td>${direction}</td>
            <td>${startDate}</td>
            <td>${endDate}</td>
            <td>${schedule.status}</td>
            <td>${cronExpression}</td>
            <td>
                <button onclick="deleteSchedule(${schedule.id})" class="btn btn-danger">Supprimer</button>
                <button onclick="editWorkload('${resourceType}', '${resourceName}', '${resourceNamespace}', '${direction}', ${schedule.id}, '${cronExpression}')" class="btn btn-primary">Modifier</button>
            </td>
        `;
        
        tableBody.appendChild(row);
    });
    
    schedulesContainer.appendChild(table);
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
function editWorkload(action, name, namespace, direction, scheduleId, cronValue) {
    currentAction = action;
    currentName = name;
    currentNamespace = namespace;
    currentDirection = direction;
    currentScheduleId = scheduleId;

    actionTypeEl.textContent = action;
    resourceNameEl.textContent = name;
    namespaceNameEl.textContent = namespace;
    directionTypeEl.textContent = direction;

    cronInput.value = cronValue === 'Non programmé' ? defaultCronValue : cronValue;
    cronError.style.display = 'none';

    document.querySelector('.modal-content h3').textContent = 'Modifier la programmation';

    saveBtn.dataset.mode = 'update';

    modal.style.display = 'block';
}