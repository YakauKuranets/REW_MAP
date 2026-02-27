import { useMemo } from 'react';
import Supercluster from 'supercluster';

const normalizeItemType = (item) => item.type || item.entityType || 'unknown';

export default function useMapClusters({ data = [], zoom = 0, bounds }) {
  return useMemo(() => {
    if (!Array.isArray(bounds) || bounds.length !== 4) return [];

    const featureCollection = {
      type: 'FeatureCollection',
      features: (Array.isArray(data) ? data : [])
        .filter((item) => Number.isFinite(Number(item?.lon)) && Number.isFinite(Number(item?.lat)))
        .map((item) => ({
          type: 'Feature',
          geometry: {
            type: 'Point',
            coordinates: [Number(item.lon), Number(item.lat)],
          },
          properties: {
            ...item,
            entityType: normalizeItemType(item),
            cluster: false,
          },
        })),
    };

    const clusterIndex = new Supercluster({ radius: 60, maxZoom: 16 });
    clusterIndex.load(featureCollection.features);

    return clusterIndex.getClusters(bounds, Math.round(zoom));
  }, [bounds, data, zoom]);
}
