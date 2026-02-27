import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';

export const initPmtiles = () => {
  let protocol = new Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile);
  return protocol;
};
