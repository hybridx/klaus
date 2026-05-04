import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { Components } from 'react-markdown';

const components: Components = {
  pre({ children }) {
    return (
      <pre className="my-2 rounded-lg bg-stone-100 dark:bg-stone-800 p-3 overflow-x-auto
                       text-[12px] leading-relaxed border border-stone-200 dark:border-stone-700">
        {children}
      </pre>
    );
  },
  code({ children, className }) {
    const isBlock = className?.startsWith('language-') || className?.startsWith('hljs');
    if (isBlock) {
      return <code className={`${className ?? ''} font-mono`}>{children}</code>;
    }
    return (
      <code className="px-1 py-0.5 rounded bg-stone-100 dark:bg-stone-800
                        text-[12px] font-mono text-stone-700 dark:text-stone-300
                        border border-stone-200 dark:border-stone-700">
        {children}
      </code>
    );
  },
  p({ children }) {
    return <p className="mb-2 last:mb-0">{children}</p>;
  },
  ul({ children }) {
    return <ul className="mb-2 ml-4 list-disc space-y-0.5">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="mb-2 ml-4 list-decimal space-y-0.5">{children}</ol>;
  },
  li({ children }) {
    return <li className="pl-0.5">{children}</li>;
  },
  h1({ children }) {
    return <h1 className="text-[16px] font-semibold mt-3 mb-1">{children}</h1>;
  },
  h2({ children }) {
    return <h2 className="text-[15px] font-semibold mt-3 mb-1">{children}</h2>;
  },
  h3({ children }) {
    return <h3 className="text-[14px] font-semibold mt-2 mb-1">{children}</h3>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-2 border-stone-300 dark:border-stone-600 pl-3 my-2
                             text-stone-500 dark:text-stone-400 italic">
        {children}
      </blockquote>
    );
  },
  table({ children }) {
    return (
      <div className="overflow-x-auto my-2">
        <table className="text-[12px] border-collapse w-full">{children}</table>
      </div>
    );
  },
  th({ children }) {
    return (
      <th className="border border-stone-200 dark:border-stone-700 px-2 py-1 text-left
                     bg-stone-50 dark:bg-stone-800 font-medium">
        {children}
      </th>
    );
  },
  td({ children }) {
    return (
      <td className="border border-stone-200 dark:border-stone-700 px-2 py-1">
        {children}
      </td>
    );
  },
  a({ children, href }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer"
         className="text-stone-600 dark:text-stone-400 underline underline-offset-2
                    hover:text-stone-900 dark:hover:text-stone-200 transition-colors">
        {children}
      </a>
    );
  },
  img({ src, alt }) {
    return (
      <img src={src} alt={alt || ''}
           className="my-2 max-w-full max-h-[400px] rounded-xl object-contain
                      border border-stone-200 dark:border-stone-700" />
    );
  },
  hr() {
    return <hr className="my-3 border-stone-200 dark:border-stone-700" />;
  },
};

export default function Markdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={components}
    >
      {content}
    </ReactMarkdown>
  );
}
