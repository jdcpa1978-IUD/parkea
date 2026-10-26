import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';

export interface User {
  id_usuario: number;
  documento: string;
  nombre: string;
  apellido: string;
  telefono: string | null;
  email: string | null;
  rol: 'ADMINISTRADOR' | 'OPERADOR' | 'CLIENTE';
  estado: 'ACTIVO' | 'INACTIVO';
}

export interface Cell {
  id_celda: number;
  codigo_celda: string;
  tipo_celda: 'AUTOMOVIL' | 'MOTOCICLETA';
  estado: 'DISPONIBLE' | 'OCUPADA' | 'MANTENIMIENTO';
}

export interface Vehicle {
  id_vehiculo: number;
  placa: string;
  tipo_vehiculo: 'AUTOMOVIL' | 'MOTOCICLETA';
  id_usuario: number;
  marca: string | null;
  modelo: string | null;
  color: string | null;
}

export interface AccessRecord {
  id_registro: number;
  id_vehiculo: number;
  placa: string;
  id_celda: number;
  codigo_celda: string;
  fecha_hora_ingreso: string;
  fecha_hora_salida: string | null;
  estado_registro: string;
}

export interface Dashboard {
  celdas_totales: number;
  celdas_ocupadas: number;
  ingresos_activos: number;
  mensualidades_vigentes: number;
}

export interface Payment {
  id_pago: number;
  id_usuario: number;
  monto: number;
  fecha_pago: string;
  fecha_inicio_vencimiento: string;
  fecha_fin_vencimiento: string;
  metodo_pago: string;
}

export interface Incident {
  id_novedad: number;
  id_registro: number;
  id_operador: number;
  descripcion: string;
  fecha_hora: string;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = 'http://localhost:8000/api';

  login(documento: string, password: string) {
    return this.http.post<{ access_token: string; user: User }>(`${this.base}/auth/login`, {
      documento,
      password,
    });
  }
  dashboard() { return this.http.get<Dashboard>(`${this.base}/dashboard`); }
  users() { return this.http.get<User[]>(`${this.base}/usuarios`); }
  clients() { return this.http.get<User[]>(`${this.base}/clientes`); }
  createUser(value: object) { return this.http.post<User>(`${this.base}/usuarios`, value); }
  deactivateUser(id: number) { return this.http.delete<void>(`${this.base}/usuarios/${id}`); }
  vehicles() { return this.http.get<Vehicle[]>(`${this.base}/vehiculos`); }
  createVehicle(value: object) { return this.http.post<Vehicle>(`${this.base}/vehiculos`, value); }
  createVehicleWithNewClient(value: object) {
    return this.http.post<{ vehiculo: Vehicle; cliente: User; clave_temporal: string }>(
      `${this.base}/vehiculos/registro-completo`, value,
    );
  }
  cells() { return this.http.get<Cell[]>(`${this.base}/celdas`); }
  createCell(value: object) { return this.http.post<Cell>(`${this.base}/celdas`, value); }
  updateCell(id: number, estado: string) {
    return this.http.patch<Cell>(`${this.base}/celdas/${id}`, { estado });
  }
  activeAccesses() { return this.http.get<AccessRecord[]>(`${this.base}/accesos/activos`); }
  entry(placa: string) { return this.http.post<AccessRecord>(`${this.base}/accesos/entrada`, { placa }); }
  exit(placa: string) { return this.http.post<Record<string, unknown>>(`${this.base}/accesos/salida`, { placa }); }
  payments() { return this.http.get<Payment[]>(`${this.base}/pagos`); }
  createPayment(value: object) { return this.http.post<Payment>(`${this.base}/pagos`, value); }
  incidents() { return this.http.get<Incident[]>(`${this.base}/novedades`); }
  createIncident(value: object) { return this.http.post<Incident>(`${this.base}/novedades`, value); }
}
