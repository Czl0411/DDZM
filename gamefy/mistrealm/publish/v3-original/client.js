import {ClassicClient,remainingSeconds} from '../classic/client.js';
export {remainingSeconds};
export class V3Client extends ClassicClient {
 constructor(options){super(options);this.root=this.sharedRoot+'/v3';}
 saveDeck({id,name,faction,leader,counts}){return super.saveDeck({id,name,faction,leader,counts});}
}
