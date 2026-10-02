import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as api from './client'
import { isTerminalStatus } from '../status'

export const queryKeys = {
  vesselTypes: ['vesselTypes'],
  vehicle: (vesselType) => ['vehicle', vesselType],
  locations: ['locations'],
  recentRoutes: ['recentRoutes'],
  job: (jobId) => ['job', jobId],
}

export const useVesselTypes = () =>
  useQuery({ queryKey: queryKeys.vesselTypes, queryFn: api.getVesselTypes, staleTime: 5 * 60_000 })

export const useVehicle = (vesselType) =>
  useQuery({
    queryKey: queryKeys.vehicle(vesselType),
    queryFn: () => api.getVehicle(vesselType),
    enabled: Boolean(vesselType) && vesselType !== 'default',
  })

export const useLocations = () =>
  useQuery({ queryKey: queryKeys.locations, queryFn: api.getLocations, staleTime: 5 * 60_000 })

// Pass refetchInterval to poll; components that don't poll still share the same cached data.
export const useRecentRoutes = ({ refetchInterval = false } = {}) =>
  useQuery({ queryKey: queryKeys.recentRoutes, queryFn: api.getRecentRoutes, refetchInterval })

// Polls until the job reaches a final state or the request fails (e.g. the job was cancelled and deleted).
export const useJob = (jobId, { interval = 2000 } = {}) =>
  useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: () => api.getJob(jobId),
    enabled: Boolean(jobId),
    retry: false,
    refetchInterval: (query) =>
      query.state.error || isTerminalStatus(query.state.data?.status) ? false : interval,
  })

export const useRequestRoute = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.requestRoute,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.recentRoutes }),
  })
}

export const useCancelJob = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.cancelJob,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.recentRoutes }),
  })
}

export const useLoadRoute = () => useMutation({ mutationFn: api.getRoute })
