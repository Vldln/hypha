import * as ActionTypes from './constants';
import initialState from './models';

/* eslint-disable default-case, no-param-reassign */
const flagContainerReducer = (state = initialState, action) => {
  switch (action.type) {
    case ActionTypes.INIT:
      return state.set(action.flagType, {
        "title" : action.title,
        "APIPath": action.APIPath,
        "loading" : false,
        "isFlagged": false
    })
    case ActionTypes.SHOW_LOADING:
      return state.setIn([action.flagType, "loading"], true);
    case ActionTypes.HIDE_LOADING:
      return state.setIn([action.flagType, "loading"], false);
    case ActionTypes.GET_SELECTED_FLAG:
      return state.setIn([action.flagType, "isFlagged"], action.data);
    case ActionTypes.SET_FLAG:
      return state.setIn([action.flagType, "isFlagged"], !state[action.flagType].isFlagged)
    default:
      return state;
  }
};

export default flagContainerReducer;
