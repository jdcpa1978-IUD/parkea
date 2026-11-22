import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { ChangeDetectorRef, Component, OnDestroy, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { interval, Subscription } from 'rxjs';
import {
  AccessRecord, ApiService, Cell, ClientCoverage, ClientHistory, Dashboard, Incident, Payment, User, UserUpdate, Vehicle,
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
  private readonly changeDetector = inject(ChangeDetectorRef);
  private poll?: Subscription;
  private liveDataRequest = 0;
  private clientCoverageRequest = 0;
  private clientHistoryRequest = 0;

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
  editingUser: User | null = null;
  clients: User[] = [];
  vehicles: Vehicle[] = [];
  payments: Payment[] = [];
  clientCoverage: ClientCoverage[] = [];
  clientCoverageLoaded = false;
  clientCoverageLoading = false;
  selectedHistoryClientId = 0;
  clientHistory: ClientHistory | null = null;
  clientHistoryLoading = false;
  incidents: Incident[] = [];

  loginForm = { documento: '', password: '' };
  accessForm = { placa: '' };
  userForm = {
    documento: '', nombre: '', apellido: '', telefono: '', email: '', password: '', rol: 'CLIENTE',
  };
  userEditForm: Omit<UserUpdate, 'password'> & { password: string } = {
    nombre: '', apellido: '', telefono: null, email: null, password: '', rol: 'CLIENTE',
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
  get clientsWithoutCoverage(): ClientCoverage[] {
    return this.clientCoverage.filter((client) => !client.vigente);
  }
  get selectedCell(): Cell | null {
    return this.cells.find((cell) => cell.id_celda === this.selectedCellId) ?? null;
  }
  get selectedCellAccess(): AccessRecord | undefined {
    return this.accesses.find((record) => record.id_celda === this.selectedCellId);
  }
  get occupiedCells(): number {
    return this.cells.filter((cell) => this.isCellOccupied(cell)).length;
  }
  get availableCells(): number {
    return this.cells.filter((cell) => cell.estado === 'DISPONIBLE').length;
  }

  isCellOccupied(cell: Cell): boolean {
    return cell.estado === 'OCUPADA' || this.hasActiveAccess(cell);
  }

  hasActiveAccess(cell: Cell): boolean {
    return this.accesses.some((record) => record.id_celda === cell.id_celda);
  }

  cellStatusLabel(cell: Cell): string {
    if (cell.estado === 'MANTENIMIENTO' && this.hasActiveAccess(cell)) {
      return 'OCUPADA · MANTENIMIENTO AL SALIR';
    }
    return cell.estado;
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
    this.clientCoverageRequest += 1;
    this.clientHistoryRequest += 1;
    this.clientCoverage = [];
    this.clientCoverageLoaded = false;
    this.clientCoverageLoading = false;
    this.selectedHistoryClientId = 0;
    this.clientHistory = null;
    this.clientHistoryLoading = false;
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
    if (this.screen === 'payments') {
      this.loadPayments();
      if (this.user?.rol !== 'CLIENTE') {
        this.loadClientCoverage();
        if (this.selectedHistoryClientId) this.loadClientHistory();
      }
    }
    if (this.screen === 'incidents') this.loadIncidents();
  }

  registerEntry(): void {
    const plate = this.normalizePlate(this.accessForm.placa);
    if (!this.isValidPlate(plate)) {
      this.showError('La placa ingresada no es válida. Debe tener exactamente 6 caracteres alfanuméricos.');
      return;
    }
    this.api.entry(plate).subscribe({
      next: (record) => {
        this.showSuccess(`Ingreso registrado: ${record.placa} → celda ${record.codigo_celda}.`);
        this.accessForm.placa = '';
        this.loadLiveData();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  registerExit(): void {
    const plate = this.normalizePlate(this.accessForm.placa);
    if (!this.isValidPlate(plate)) {
      this.showError('La placa ingresada no es válida. Debe tener exactamente 6 caracteres alfanuméricos.');
      return;
    }
    if (!confirm(`¿Confirmas la salida del vehículo ${plate}?`)) return;
    this.api.exit(plate).subscribe({
      next: (result) => {
        this.showSuccess(
          `Salida registrada: ${result.placa}, celda ${result.codigo_celda}. ` +
          `Permanencia: ${this.formatDuration(result.minutos_permanencia)}.`,
        );
        this.accessForm.placa = '';
        this.loadLiveData();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  registerExitFor(access: AccessRecord): void {
    this.accessForm.placa = access.placa;
    this.registerExit();
  }

  createUser(): void {
    const { password, ...user } = this.userForm;
    this.api.createUser({
      ...user,
      ...(user.rol === 'CLIENTE' ? {} : { password }),
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

  startEditingUser(user: User): void {
    this.editingUser = user;
    this.userEditForm = {
      nombre: user.nombre,
      apellido: user.apellido,
      telefono: user.telefono,
      email: user.email,
      password: '',
      rol: user.rol,
    };
    this.message = '';
  }

  cancelUserEdit(): void {
    this.editingUser = null;
    this.message = '';
  }

  updateUser(): void {
    const user = this.editingUser;
    if (!user) return;

    const update: UserUpdate = {
      nombre: this.userEditForm.nombre.trim(),
      apellido: this.userEditForm.apellido.trim(),
      telefono: this.userEditForm.telefono?.trim() || null,
      email: this.userEditForm.email?.trim() || null,
    };
    if (this.userEditForm.rol !== 'CLIENTE' && this.userEditForm.password) update.password = this.userEditForm.password;
    const isCurrentUser = user.id_usuario === this.user?.id_usuario;
    if (!isCurrentUser) update.rol = this.userEditForm.rol;

    this.api.updateUser(user.id_usuario, update).subscribe({
      next: (updated) => {
        if (isCurrentUser) {
          this.user = updated;
          localStorage.setItem('parkea_user', JSON.stringify(updated));
        }
        this.editingUser = null;
        this.showSuccess('Usuario actualizado correctamente.');
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

  activateUser(user: User): void {
    if (!confirm(`¿Activar a ${user.nombre} ${user.apellido}?`)) return;
    this.api.updateUser(user.id_usuario, { estado: 'ACTIVO' }).subscribe({
      next: () => {
        this.showSuccess('Usuario activado.');
        this.loadUsers();
      },
      error: (error: unknown) => this.showError(error),
    });
  }

  createVehicle(): void {
    const plate = this.normalizePlate(this.vehicleForm.placa);
    if (!this.isValidPlate(plate)) {
      this.showError('La placa ingresada no es válida. Debe tener exactamente 6 caracteres alfanuméricos.');
      return;
    }
    const vehicle = {
      placa: plate,
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
        next: ({ cliente }) => {
          this.resetVehicleForm(cliente.id_usuario);
          this.loadClients();
          this.showSuccess(`Cliente ${cliente.nombre} y vehículo registrados.`);
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

  setCellStatus(cell: Cell, estado: Cell['estado']): void {
    if (
      cell.estado === 'OCUPADA'
      && estado === 'MANTENIMIENTO'
      && !confirm(`¿Programar mantenimiento para ${cell.codigo_celda} después de la salida?`)
    ) {
      return;
    }
    this.api.updateCell(cell.id_celda, estado).subscribe({
      next: (updatedCell) => {
        this.liveDataRequest += 1;
        this.cells = this.cells.map((item) =>
          item.id_celda === updatedCell.id_celda ? updatedCell : item,
        );
        this.changeDetector.markForCheck();
        this.showSuccess(
          cell.estado === 'OCUPADA'
            ? `La celda ${cell.codigo_celda} quedará en mantenimiento al registrar la salida.`
            : `Estado de ${cell.codigo_celda} actualizado.`,
        );
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

  private normalizePlate(value: string): string {
    return value.trim().toUpperCase();
  }

  private isValidPlate(value: string): boolean {
    return /^[A-Z0-9]{6}$/.test(value);
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
    const monto = Number(this.paymentForm.monto);
    if (!Number.isFinite(monto) || monto <= 0) {
      this.showError('Monto inválido. Debe ser mayor que cero.');
      return;
    }
    if (Number(monto.toFixed(2)) !== monto) {
      this.showError('Monto inválido. Debe tener máximo dos decimales.');
      return;
    }
    const meses = Number(this.paymentForm.meses);
    if (!Number.isInteger(meses) || meses < 1 || meses > 24) {
      this.showError('Meses inválidos. Ingresa un número entero entre 1 y 24.');
      return;
    }

    this.api.createPayment({
      ...this.paymentForm,
      id_usuario: Number(this.paymentForm.id_usuario),
      monto,
      meses,
    }).subscribe({
      next: (payment) => {
        this.paymentForm = { id_usuario: 0, monto: 0, meses: 1, metodo_pago: 'EFECTIVO' };
        this.showSuccess(`Pago registrado. Vigencia hasta ${payment.fecha_fin_vencimiento}.`);
        this.loadPayments();
        this.loadLiveData();
        this.loadClientCoverage();
        if (this.selectedHistoryClientId) this.loadClientHistory();
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

  private formatDuration(minutes: number): string {
    const hours = Math.floor(minutes / 60);
    const remainingMinutes = minutes % 60;
    return hours ? `${hours} h ${remainingMinutes} min` : `${remainingMinutes} min`;
  }

  private readSessionUser(): User | null {
    try {
      const saved = localStorage.getItem('parkea_user');
      if (!saved || !localStorage.getItem('parkea_token')) return null;
      const user = JSON.parse(saved) as User;
      if (user.rol === 'CLIENTE') {
        localStorage.removeItem('parkea_user');
        localStorage.removeItem('parkea_token');
        return null;
      }
      return user;
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
    const requestId = ++this.liveDataRequest;
    this.api.cells().subscribe({
      next: (items) => {
        if (requestId !== this.liveDataRequest) return;
        this.cells = items;
        if (!items.some((cell) => cell.id_celda === this.selectedCellId)) {
          this.selectedCellId = items[0]?.id_celda ?? 0;
        }
        this.changeDetector.markForCheck();
      },
      error: (error: unknown) => {
        if (requestId === this.liveDataRequest) this.showError(error);
      },
    });
    this.api.activeAccesses().subscribe({
      next: (items) => {
        if (requestId === this.liveDataRequest) this.accesses = items;
        this.changeDetector.markForCheck();
      },
      error: (error: unknown) => {
        if (requestId === this.liveDataRequest) this.showError(error);
      },
    });
    this.api.dashboard().subscribe({
      next: (data) => {
        if (requestId === this.liveDataRequest) this.dashboard = data;
        this.changeDetector.markForCheck();
      },
      error: (error: unknown) => {
        if (requestId === this.liveDataRequest) this.showError(error);
      },
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

  private loadClientCoverage(): void {
    const requestId = ++this.clientCoverageRequest;
    this.clientCoverageLoaded = false;
    this.clientCoverageLoading = true;
    this.api.clientCoverage().subscribe({
      next: (clients) => {
        if (requestId !== this.clientCoverageRequest) return;
        this.clientCoverage = clients;
        this.clientCoverageLoaded = true;
        this.clientCoverageLoading = false;
      },
      error: (error: unknown) => {
        if (requestId !== this.clientCoverageRequest) return;
        this.clientCoverageLoading = false;
        this.showError(error);
      },
    });
  }

  showClientHistory(clientId: number): void {
    this.selectedHistoryClientId = clientId;
    this.loadClientHistory();
  }

  loadClientHistory(): void {
    const clientId = Number(this.selectedHistoryClientId);
    const requestId = ++this.clientHistoryRequest;
    this.clientHistory = null;
    this.clientHistoryLoading = false;
    if (!clientId) return;
    this.clientHistoryLoading = true;
    this.api.clientHistory(clientId).subscribe({
      next: (history) => {
        if (requestId !== this.clientHistoryRequest) return;
        this.clientHistory = history;
        this.clientHistoryLoading = false;
      },
      error: (error: unknown) => {
        if (requestId !== this.clientHistoryRequest) return;
        this.clientHistoryLoading = false;
        this.showError(error);
      },
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
    this.message = typeof error === 'string'
      ? error
      : error instanceof HttpErrorResponse
        ? (typeof error.error?.detail === 'string' ? error.error.detail : 'No se pudo conectar con PARKEA. Verifica el servidor.')
        : 'Ocurrió un error inesperado.';
    this.messageIsError = true;
  }
}
