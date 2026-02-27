import React from 'react';

export default function DeckGL({ children }) {
  return <div className="h-full w-full">{children}</div>;
}

export class IconLayer {
  constructor(props) {
    this.props = props;
  }
}

export class HexagonLayer {
  constructor(props) {
    this.props = props;
  }
}
