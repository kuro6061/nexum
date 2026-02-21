import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const PROTO_PATH = resolve(__dirname, '..', '..', '..', 'proto', 'nexum.proto');

const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: false,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});

const proto = grpc.loadPackageDefinition(packageDefinition) as any;

export function createNexumClient(address: string) {
  return new proto.nexum.NexumService(
    address,
    grpc.credentials.createInsecure()
  );
}

export function promisify<TReq, TRes>(
  client: any,
  method: string
): (req: TReq) => Promise<TRes> {
  return (req: TReq) =>
    new Promise<TRes>((resolve, reject) => {
      client[method](req, (err: any, res: TRes) => {
        if (err) reject(err);
        else resolve(res);
      });
    });
}
