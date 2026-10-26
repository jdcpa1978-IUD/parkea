import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { interval, Subscription } from 'rxjs';
import {
  AccessRecord, ApiService, Cell, Dashboard, Incident, Payment, User, Vehicle,
} from './api.service';

type Screen = 'dashboard' | 'access' | 'cells' | 'users' | 'vehicles' | 'payments' | 'incidents';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
})
export class AppComponent implements OnInit, OnDestroy {
  private readonly api = inject(ApiService);
  private poll?: Subscription;

  user: User | null = this.readSessionUser();
  screen: Screen = 'dashboard';
  message = '';
  messageIsError = false;
  dashboard: Dashboard = {
    celdas_totales: 0, celdas_ocupadas: 0, ingresos_activos: 0, mensualidades_vigentes: 0,
  };
  cells: Cell[] = [];
  selectedCellId = 0;
  accesses: AccessRecord[] = [];
  users: User[] = [];
  clients: User[] = [];
  vehicles: Vehicle[] = [];
  payments: Payment[] = [];
  incidents: Incident[] = [];

  loginForm = { documento: '', password: '' };
  accessForm = { placa: '' };
  userForm = {
    documento: '', nombre: '', apellido: '', telefono: '', email: '', password: '', rol: 'CLIENTE',
  };
  vehicleForm = {
    placa: '', tipo_vehiculo: 'AUTOMOVIL', id_usuario: -1, marca: '', modelo: '', color: '',
    cliente: {
      documento: '', nombre_completo: '',
    },
  };
  cellForm = { codigo_celda: '', tipo_celda: 'AUTOMOVIL' };
  paymentForm = { id_usuario: 0, monto: 0, meses: 1, metodo_pago: 'EFECTIVO' };
  incidentForm = { id_registro: 0, descripcion: '' };

  ngOnInit(): void {
    if (this.user) this.loadWorkspace();
    this.poll = interval(15000).subscribe(() => {
      if (this.user) this.loadLiveData();
    });
  }

  ngOnDestroy(): void {
    this.poll?.unsubscribe();
  }

  get isAdmin(): boolean { return this.user?.rol === 'ADMINISTRADOR'; }
  get selectedCell(): Cell | null {
    return this.cells.find((cell) => cell.id_celda === this.selectedCellId) ?? null;
  }
  get selectedCellAccess(): AccessRecord | undefined {
    return this.accesses.find((record) => record.id_celda === this.selectedCellId);
  }
  get occupiedCells(): number {
    return this.cells.filter((cell) => cell.estado === 'OCUPADA').length;
  }
  get availableCells(): number {
    return this.cells.filter((cell) => cell.estado === 'DISPONIBLE').length;
  }

  login(): void {
    this.message = '';
    this.api.login(this.loginForm.documento.trim(), this.loginForm.password).subscribe({
      next: (result) => {
        localStorage.setItem('parkea_token', result.access_token);
        localStorage.setItem('parkea_user', JSON.stringify(result.user));
        this.user = result.user;
        this.loginForm.password = '';
        this.loadWorkspace();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  logout(): void {
    localStorage.removeItem('parkea_token');
    localStorage.removeItem('parkea_user');
    this.user = null;
    this.screen = 'dashboard';
    this.message = '';
  }

  navigate(screen: Screen): void {
    this.screen = screen;
    this.message = '';
    this.refreshScreen();
  }

  refreshScreen(): void {
    this.loadLiveData();
    if (this.isAdmin && (this.screen === 'users' || this.screen === 'vehicles')) this.loadUsers();
    if (this.screen === 'vehicles') this.loadVehicles();
    if (this.screen === 'payments') this.loadPayments();
    if (this.screen === 'incidents') this.loadIncidents();
  }

  registerEntry(): void {
    this.api.entry(this.accessForm.placa.trim().toUpperCase()).subscribe({
      next: (record) => {
        this.showSuccess(`Ingreso registrado: ${record.placa} → celda ${record.codigo_celda}.`);
        this.accessForm.placa = '';
        this.loadLiveData();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  registerExit(): void {
    this.api.exit(this.accessForm.placa.trim().toUpperCase()).subscribe({
      next: (result) => {
        this.showSuccess(`Salida registrada. Permanencia: ${result['minutos_permanencia']} minutos.`);
        this.accessForm.placa = '';
        this.loadLiveData();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  createUser(): void {
    this.api.createUser({
      ...this.userForm,
      telefono: this.userForm.telefono || null,
      email: this.userForm.email || null,
    }).subscribe({
      next: () => {
        this.userForm = {
          documento: '', nombre: '', apellido: '', telefono: '', email: '', password: '', rol: 'CLIENTE',
        };
        this.showSuccess('Usuario creado correctamente.');
        this.loadUsers();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  deactivateUser(user: User): void {
    if (!confirm(`¿Desactivar a ${user.nombre} ${user.apellido}?`)) return;
    this.api.deactivateUser(user.id_usuario).subscribe({
      next: () => {
        this.showSuccess('Usuario desactivado.');
        this.loadUsers();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  createVehicle(): void {
    const vehicle = {
      placa: this.vehicleForm.placa.trim().toUpperCase(),
      tipo_vehiculo: this.vehicleForm.tipo_vehiculo,
      marca: this.vehicleForm.marca || null,
      modelo: this.vehicleForm.modelo || null,
      color: this.vehicleForm.color || null,
    };
    if (this.vehicleForm.id_usuario === -1) {
      this.api.createVehicleWithNewClient({
        ...vehicle,
        cliente: {
          documento: this.vehicleForm.cliente.documento.trim(),
          nombre_completo: this.vehicleForm.cliente.nombre_completo.trim(),
        },
      }).subscribe({
        next: ({ cliente, clave_temporal }) => {
          this.resetVehicleForm(cliente.id_usuario);
          this.loadClients();
          this.showSuccess(
            `Cliente ${cliente.nombre} y vehículo registrados. Clave inicial (cópiala; solo se muestra una vez): ${clave_temporal}`,
          );
          this.loadVehicles();
        },
        error: (error: unknown) => this.showError(error),
      });
      return;
    }
    this.api.createVehicle({
      ...vehicle,
      id_usuario: Number(this.vehicleForm.id_usuario),
    }).subscribe({
      next: () => {
        this.resetVehicleForm();
        this.showSuccess('Vehículo registrado correctamente.');
        this.loadVehicles();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  private resetVehicleForm(ownerId = this.clients[0]?.id_usuario ?? -1): void {
    this.vehicleForm = {
      placa: '', tipo_vehiculo: 'AUTOMOVIL', id_usuario: ownerId,
      marca: '', modelo: '', color: '',
      cliente: { documento: '', nombre_completo: '' },
    };
  }

  createCell(): void {
    this.api.createCell(this.cellForm).subscribe({
      next: () => {
        this.cellForm = { codigo_celda: '', tipo_celda: 'AUTOMOVIL' };
        this.showSuccess('Celda creada.');
        this.loadLiveData();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  setCellStatus(cell: Cell, estado: string): void {
    this.api.updateCell(cell.id_celda, estado).subscribe({
      next: () => {
        this.showSuccess(`Estado de ${cell.codigo_celda} actualizado.`);
        this.loadLiveData();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  selectCell(cell: Cell): void {
    this.selectedCellId = cell.id_celda;
  }

  validatePlateInput(event: InputEvent): void {
    const character = event.data;
    if (character && !/^[a-zA-Z0-9]+$/.test(character)) {
      event.preventDefault();
    }
  }

  sanitizePlateInput(event: Event, field: 'access' | 'vehicle'): void {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    const plate = input.value.replace(/[^a-zA-Z0-9]/g, '').slice(0, 6).toUpperCase();
    if (input.value !== plate) {
      input.value = plate;
    }
    if (field === 'access') {
      this.accessForm.placa = plate;
    } else {
      this.vehicleForm.placa = plate;
    }
  }

  pastePlate(event: ClipboardEvent, field: 'access' | 'vehicle'): void {
    event.preventDefault();
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    const pasted = event.clipboardData?.getData('text') ?? '';
    const start = input.selectionStart ?? input.value.length;
    const end = input.selectionEnd ?? start;
    const current = input.value.slice(0, start) + input.value.slice(end);
    const room = Math.max(0, 6 - current.length);
    const inserted = pasted.replace(/[^a-zA-Z0-9]/g, '').slice(0, room).toUpperCase();
    input.setRangeText(inserted, start, end, 'end');
    this.sanitizePlateInput(event, field);
  }

  createPayment(): void {
    this.api.createPayment({
      ...this.paymentForm,
      id_usuario: Number(this.paymentForm.id_usuario),
      monto: Number(this.paymentForm.monto),
      meses: Number(this.paymentForm.meses),
    }).subscribe({
      next: (payment) => {
        this.showSuccess(`Pago registrado. Vigencia hasta ${payment.fecha_fin_vencimiento}.`);
        this.loadPayments();
        this.loadLiveData();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  createIncident(): void {
    this.api.createIncident({
      ...this.incidentForm,
      id_registro: Number(this.incidentForm.id_registro),
    }).subscribe({
      next: () => {
        this.incidentForm = { id_registro: 0, descripcion: '' };
        this.showSuccess('Novedad registrada.');
        this.loadIncidents();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  formatDate(value: string | null): string {
    return value ? new Date(value).toLocaleString('es-CO') : '—';
  }

  private readSessionUser(): User | null {
    try {
      const saved = localStorage.getItem('parkea_user');
      return saved && localStorage.getItem('parkea_token') ? JSON.parse(saved) as User : null;
    } catch {
      localStorage.removeItem('parkea_user');
      localStorage.removeItem('parkea_token');
      return null;
    }
  }

  private loadWorkspace(): void {
    this.loadLiveData();
    if (this.user?.rol !== 'CLIENTE') {
      this.loadClients();
      this.loadIncidents();
    }
    if (this.isAdmin) this.loadUsers();
    this.loadVehicles();
    this.loadPayments();
  }

  private loadLiveData(): void {
    this.api.cells().subscribe({
      next: (items) => {
        this.cells = items;
        if (!items.some((cell) => cell.id_celda === this.selectedCellId)) {
          this.selectedCellId = items[0]?.id_celda ?? 0;
        }
      },
      error: (error: unknown) => this.showError(error),
    });
    this.api.activeAccesses().subscribe({
      next: (items) => { this.accesses = items; },
      error: (error: unknown) => this.showError(error),
    });
    this.api.dashboard().subscribe({
      next: (data) => { this.dashboard = data; },
      error: (error: unknown) => this.showError(error),
    });
  }

  private loadUsers(): void {
    this.api.users().subscribe({
      next: (items) => { this.users = items; },
      error: (error: unknown) => this.showError(error),
    });
  }

  private loadClients(): void {
    this.api.clients().subscribe({
      next: (items) => {
        this.clients = items;
        if (!items.length && this.vehicleForm.id_usuario === 0) {
          this.vehicleForm.id_usuario = -1;
        }
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  private loadVehicles(): void {
    this.api.vehicles().subscribe({
      next: (items) => { this.vehicles = items; },
      error: (error: unknown) => this.showError(error),
    });
  }

  private loadPayments(): void {
    this.api.payments().subscribe({
      next: (items) => { this.payments = items; },
      error: (error: unknown) => this.showError(error),
    });
  }

  private loadIncidents(): void {
    this.api.incidents().subscribe({
      next: (items) => { this.incidents = items; },
      error: (error: unknown) => this.showError(error),
    });
  }

  private showSuccess(text: string): void {
    this.message = text;
    this.messageIsError = false;
  }

  private showError(error: unknown): void {
    this.message = error instanceof HttpErrorResponse
      ? (typeof error.error?.detail === 'string' ? error.error.detail : 'No se pudo conectar con PARKEA. Verifica el servidor.')
      : 'Ocurrió un error inesperado.';
    this.messageIsError = true;
  }
}
