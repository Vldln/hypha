import * as ActionTypes from './constants';

export const initAction = (flagType, title, APIPath, submissionID) => ({
  type: ActionTypes.INIT,
  flagType,
  title,
  APIPath,
  submissionID
})

export const showLoadingAction = (flagType) => ({
  type: ActionTypes.SHOW_LOADING,
  flagType
})

export const hideLoadingAction = (flagType) => ({
  type: ActionTypes.HIDE_LOADING,
  flagType
})

export const getSelectedFlagAction = (flagType, data) => ({
  type: ActionTypes.GET_SELECTED_FLAG,
  flagType,
  data
})

export const setFlagAction = (flagType, APIPath) => ({
  type: ActionTypes.SET_FLAG,
  flagType,
  APIPath
})
